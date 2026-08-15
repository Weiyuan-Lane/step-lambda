import logging
import os
from typing import Any

import boto3

from step_lambda.utils.context import PROCESSING_BEDROCK, PROCESSING_SES_EMAIL, Context
from step_lambda.utils.errors import PipelineError
from step_lambda.processing_steps.processing_step import ProcessingStep

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Edit here: each task type maps to exactly one fixed filename.
# Keep SYSTEM_PROMPT's catalog list in sync when you change this.
# ---------------------------------------------------------------------------
TASK_CATALOG: dict[str, str] = {
    "invoice_import": "invoice_import.csv",
    "payroll_sync": "payroll_sync.csv",
    "inventory_update": "inventory_update.csv",
    "customer_export": "customer_export.csv",
    "ledger_reconcile": "ledger_reconcile.csv",
}

TOOL_NAME = "extract_tasks_from_email"

SYSTEM_PROMPT = """You extract processing tasks from email notifications.

Allowed task types and their fixed filenames (always use this exact pairing):
- invoice_import → invoice_import.csv
- payroll_sync → payroll_sync.csv
- inventory_update → inventory_update.csv
- customer_export → customer_export.csv
- ledger_reconcile → ledger_reconcile.csv

Rules:
1. Call the extract_tasks_from_email tool exactly once.
2. Return all matching tasks in that single call as the tasks array (use [] if none match).
3. Each task must use one of the allowed types above and its matching fixed filename.
4. Do not invent new task types or filenames.
5. Only include types that clearly apply to the email.
6. Use Email received date as the reference for relative dates in the body
   (e.g. "tomorrow", "next Monday", "end of month", "in 2 hours").
7. For process_date:
   - ISO 8601 datetime when a specific time is known (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS, optional timezone)
   - "now" if the task should be processed immediately
   - "null" if no process date/time can be determined
"""

TOOL_CONFIG: dict[str, Any] = {
    "tools": [
        {
            "toolSpec": {
                "name": TOOL_NAME,
                "description": (
                    "Extract matching tasks from an email notification. "
                    "Each task must be one of the allowed types with its fixed filename, "
                    "plus when it should be processed."
                ),
                "inputSchema": {
                    "json": {
                        "type": "object",
                        "properties": {
                            "tasks": {
                                "type": "array",
                                "description": "Tasks to process, derived from the email notification.",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "type": {
                                            "type": "string",
                                            "enum": list(TASK_CATALOG.keys()),
                                            "description": "Task type from the allowed catalog.",
                                        },
                                        "filename": {
                                            "type": "string",
                                            "enum": list(TASK_CATALOG.values()),
                                            "description": (
                                                "Fixed filename for the chosen task type "
                                                "(must match the catalog pairing)."
                                            ),
                                        },
                                        "process_date": {
                                            "type": "string",
                                            "description": (
                                                "When this task should be processed: ISO 8601 "
                                                "(YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS, with optional timezone); "
                                                "'now' if it should be processed immediately; "
                                                "or 'null' if no date is found."
                                            ),
                                        },
                                    },
                                    "required": ["type", "filename", "process_date"],
                                },
                            },
                        },
                        "required": ["tasks"],
                    }
                },
            }
        }
    ],
    "toolChoice": {"tool": {"name": TOOL_NAME}},
}


class BedrockProcessingStep(ProcessingStep):
    name = "bedrock"

    def __init__(self, bedrock_client: Any | None = None) -> None:
        self._bedrock_client = bedrock_client
        self._model_id = os.getenv("BEDROCK_MODEL_ID", "anthropic.claude-3-haiku-20240307-v1:0")
        self._max_tokens = int(os.getenv("BEDROCK_MAX_TOKENS", "1024"))

    @property
    def _bedrock(self) -> Any:
        if self._bedrock_client is None:
            self._bedrock_client = boto3.client("bedrock-runtime")
        return self._bedrock_client

    def process(self, event: dict[str, Any], context: Context) -> Context:
        ses_email = context.get(PROCESSING_SES_EMAIL) or {}
        user_prompt = self._build_user_prompt(ses_email)

        logger.info("Invoking Bedrock model=%s", self._model_id)
        fields = self._invoke_structured(user_prompt)

        tasks = fields.get("tasks")
        if not isinstance(tasks, list):
            tasks = []

        context.set(PROCESSING_BEDROCK, {"tasks": tasks})
        return context

    @staticmethod
    def _attachment_names(attachments: list[Any]) -> list[str]:
        return [
            item["filename"]
            for item in attachments
            if isinstance(item, dict) and item.get("filename")
        ]

    @staticmethod
    def _format_attachments_section(attachment_names: list[str]) -> str:
        if not attachment_names:
            return "Attachments: (none)"
        return "Attachments:\n" + "\n".join(f"- {name}" for name in attachment_names)

    @classmethod
    def _build_user_prompt(cls, ses_email: dict[str, Any]) -> str:
        received_date = ses_email.get("date") or "(unknown)"
        body = ses_email.get("body") or ""
        attachment_names = cls._attachment_names(ses_email.get("attachments") or [])
        attachments_section = cls._format_attachments_section(attachment_names)
        return (
            f"Email received date: {received_date}\n\n"
            f"Email body:\n{body}\n\n"
            f"{attachments_section}"
        )

    def _invoke_structured(self, user_prompt: str) -> dict[str, Any]:
        """Call Bedrock Converse with a forced tool so the model returns JSON fields."""
        response = self._bedrock.converse(
            modelId=self._model_id,
            system=[{"text": SYSTEM_PROMPT}],
            messages=[{"role": "user", "content": [{"text": user_prompt}]}],
            inferenceConfig={"maxTokens": self._max_tokens},
            toolConfig=TOOL_CONFIG,
        )

        parts = response.get("output", {}).get("message", {}).get("content", [])
        for part in parts:
            tool_use = part.get("toolUse")
            if not tool_use:
                continue
            if tool_use.get("name") != TOOL_NAME:
                continue
            raw_input = tool_use.get("input") or {}
            if isinstance(raw_input, dict):
                logger.info(
                    "Bedrock tool=%s stopReason=%s keys=%s",
                    TOOL_NAME,
                    response.get("stopReason"),
                    sorted(raw_input.keys()),
                )
                return raw_input

        # Model ignored toolChoice (rare / unsupported models).
        raise PipelineError(f"Bedrock returned no toolUse for {TOOL_NAME}")
