import json
import logging
import os
from typing import Any

import boto3

from step_lambda.utils.context import Context
from step_lambda.processing_steps.processing_step import ProcessingStep

logger = logging.getLogger(__name__)

class BedrockProcessingStep(ProcessingStep):
    name = "bedrock"

    def __init__(self, bedrock_client: Any | None = None) -> None:
        self._bedrock_client = bedrock_client

    @property
    def _bedrock(self) -> Any:
        if self._bedrock_client is None:
            self._bedrock_client = boto3.client("bedrock-runtime")
        return self._bedrock_client

    def process(self, event: dict[str, Any], context: Context) -> Context:
        key = os.getenv("BEDROCK_CONTEXT_KEY", "main")
        prompt_body = context.require(key)
        model_id = os.getenv("BEDROCK_MODEL_ID", "anthropic.claude-3-haiku-20240307-v1:0")
        system_prompt = os.getenv(
            "BEDROCK_SYSTEM_PROMPT",
            "You are an incident triage assistant. Summarize the input clearly, "
            "extract severity if possible, and suggest a short action title.",
        )
        max_tokens = int(os.getenv("BEDROCK_MAX_TOKENS", "1024"))

        logger.info("Invoking Bedrock model=%s context_key=%s", model_id, key)
        text = self._invoke(model_id, system_prompt, str(prompt_body), max_tokens)

        context.set("bedrock_response", text)
        context.set("summary", text)
        if context.get("title") is None:
            context.set("title", self._first_line(text) or context.get("email_subject"))
        return context

    def _invoke(self, model_id: str, system: str, user_text: str, max_tokens: int) -> str:
        # Prefer the Converse API (model-agnostic). Fall back to invoke_model for older runtimes.
        if hasattr(self._bedrock, "converse"):
            try:
                response = self._bedrock.converse(
                    modelId=model_id,
                    system=[{"text": system}],
                    messages=[{"role": "user", "content": [{"text": user_text}]}],
                    inferenceConfig={"maxTokens": max_tokens},
                )
                parts = response.get("output", {}).get("message", {}).get("content", [])
                return "\n".join(p.get("text", "") for p in parts if "text" in p).strip()
            except Exception as exc:
                logger.info(
                    "Converse failed for %s (%s); falling back to invoke_model",
                    model_id,
                    type(exc).__name__,
                )

        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": user_text}],
        }
        raw = self._bedrock.invoke_model(
            modelId=model_id,
            contentType="application/json",
            accept="application/json",
            body=json.dumps(body),
        )
        payload = json.loads(raw["body"].read())
        content = payload.get("content") or []
        return "\n".join(c.get("text", "") for c in content if c.get("type") == "text").strip()

    @staticmethod
    def _first_line(text: str) -> str:
        for line in text.splitlines():
            cleaned = line.strip().lstrip("#").strip()
            if cleaned:
                return cleaned[:200]
        return ""
