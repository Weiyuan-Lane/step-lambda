import logging
import os
from typing import Any

import boto3

from step_lambda.utils.context import PROCESSING_SES_EMAIL, Context
from step_lambda.processing_steps.processing_step import ProcessingStep

logger = logging.getLogger(__name__)

class BedrockProcessingStep(ProcessingStep):
    name = "bedrock"

    def __init__(self, bedrock_client: Any | None = None) -> None:
        self._bedrock_client = bedrock_client
        self._context_key = os.getenv("BEDROCK_CONTEXT_KEY", "main")
        self._model_id = os.getenv("BEDROCK_MODEL_ID", "anthropic.claude-3-haiku-20240307-v1:0")
        self._system_prompt = os.getenv(
            "BEDROCK_SYSTEM_PROMPT",
            "You are an incident triage assistant. Summarize the input clearly, "
            "extract severity if possible, and suggest a short action title.",
        )
        self._max_tokens = int(os.getenv("BEDROCK_MAX_TOKENS", "1024"))

    @property
    def _bedrock(self) -> Any:
        if self._bedrock_client is None:
            self._bedrock_client = boto3.client("bedrock-runtime")
        return self._bedrock_client

    def process(self, event: dict[str, Any], context: Context) -> Context:
        ses_email = context.get(PROCESSING_SES_EMAIL)
        if ses_email is None:
            ses_email = {}

        if self._context_key in ses_email:
            prompt_body = ses_email.get(self._context_key)
        else:
            prompt_body = context.get(self._context_key)

        if prompt_body is None:
            raise KeyError(f"Required context key missing: {self._context_key!r}")

        logger.info("Invoking Bedrock model=%s context_key=%s", self._model_id, self._context_key)
        text = self._invoke(str(prompt_body))

        context.set("bedrock_response", text)
        context.set("summary", text)
        if context.get("title") is None:
            title = self._first_line(text)
            if not title:
                title = ses_email.get("subject")
            context.set("title", title)
        return context

    def _invoke(self, user_text: str) -> str:
        response = self._bedrock.converse(
            modelId=self._model_id,
            system=[{"text": self._system_prompt}],
            messages=[{"role": "user", "content": [{"text": user_text}]}],
            inferenceConfig={"maxTokens": self._max_tokens},
        )
        parts = response.get("output", {}).get("message", {}).get("content", [])
        return "\n".join(p.get("text", "") for p in parts if "text" in p).strip()

    @staticmethod
    def _first_line(text: str) -> str:
        for line in text.splitlines():
            cleaned = line.strip().lstrip("#").strip()
            if cleaned:
                return cleaned[:200]
        return ""
