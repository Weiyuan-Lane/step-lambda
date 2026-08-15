import json
import logging
import os
from typing import Any

import boto3

from step_lambda.utils.context import PROCESSING_BEDROCK, PROCESSING_SES_EMAIL, Context
from step_lambda.utils.errors import PipelineError
from step_lambda.processing_steps.processing_step import ProcessingStep

logger = logging.getLogger(__name__)

SUCCESS_STOP_REASON = "end_turn"

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

SYSTEM_PROMPT = """You extract processing tasks from email notifications.

Allowed task types and their fixed filenames (always use this exact pairing):
- invoice_import → invoice_import.csv
- payroll_sync → payroll_sync.csv
- inventory_update → inventory_update.csv
- customer_export → customer_export.csv
- ledger_reconcile → ledger_reconcile.csv

Rules:
1. Return a single JSON object that matches the provided schema.
2. Return all matching tasks in the tasks array (use [] if none match).
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

OUTPUT_SCHEMA: dict[str, Any] = {
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
                "additionalProperties": False,
            },
        },
    },
    "required": ["tasks"],
    "additionalProperties": False,
}

OUTPUT_CONFIG: dict[str, Any] = {
    "textFormat": {
        "type": "json_schema",
        "structure": {
            "jsonSchema": {
                "schema": json.dumps(OUTPUT_SCHEMA),
                "name": "extract_tasks_from_email",
                "description": (
                    "Extract matching tasks from an email notification. "
                    "Each task must be one of the allowed types with its fixed filename, "
                    "plus when it should be processed."
                ),
            }
        },
    }
}

DEFAULT_MODEL_ID = "global.anthropic.claude-haiku-4-5-20251001-v1:0"

# -------------------------------------------------------------
# End of edit area
# -------------------------------------------------------------


class BedrockProcessingStep(ProcessingStep):
    name = "bedrock"

    def __init__(self) -> None:
        self._bedrock_client = boto3.client("bedrock-runtime")
        self._model_id = os.getenv("BEDROCK_MODEL_ID", DEFAULT_MODEL_ID)
        self._max_tokens = int(os.getenv("BEDROCK_MAX_TOKENS", "1024"))

    def process(self, event: dict[str, Any], context: Context) -> Context:
        ses_email = context.get(PROCESSING_SES_EMAIL) or {}
        user_prompt = self._build_user_prompt(ses_email)

        # Invoke Bedrock model
        logger.info("Invoking Bedrock model=%s", self._model_id)
        response = self._bedrock_client.converse(
            modelId=self._model_id,
            system=[{"text": SYSTEM_PROMPT}],
            messages=[{"role": "user", "content": [{"text": user_prompt}]}],
            inferenceConfig={"maxTokens": self._max_tokens},
            outputConfig=OUTPUT_CONFIG,
        )

        # Validate response
        stop_reason = response.get("stopReason")
        if stop_reason != SUCCESS_STOP_REASON:
            raise PipelineError(
                f"Bedrock structured output is not complete (stopReason={stop_reason!r})"
            )

        fields = self._parse_structured_json(response)
        tasks = fields.get("tasks")
        if not isinstance(tasks, list):
            tasks = []

        context.set(PROCESSING_BEDROCK, {"tasks": tasks})
        return context

    @staticmethod
    def _build_user_prompt(ses_email: dict[str, Any]) -> str:
        received_date = ses_email.get("date") or "(unknown)"
        body = ses_email.get("body") or ""

        # Build attachments section
        attachment_names = []
        for item in ses_email.get("attachments") or []:
            if isinstance(item, dict) and item.get("filename"):
                attachment_names.append(item["filename"])
        attachments_section = (
            "Attachments:\n" + "\n".join(f"- {name}" for name in attachment_names)
            if attachment_names
            else "Attachments: (none)"
        )

        # Build user prompt with rest of email content
        return (
            f"Email received date: {received_date}\n\n"
            f"Email body:\n{body}\n\n"
            f"{attachments_section}"
        )

    @staticmethod
    def _parse_structured_json(response: dict[str, Any]) -> dict[str, Any]:
        parts = response.get("output", {}).get("message", {}).get("content")
        if not isinstance(parts, list) or not parts:
            raise PipelineError("Bedrock structured output missing message content")

        # Get the stringified JSON object/array from the response (other parts like tool use are ignored)
        raw_text = ''
        for part in parts:
            if not isinstance(part, dict) or not isinstance(part.get("text"), str):
                continue
            raw_text = part["text"].strip()
            if raw_text:
                break
        if not raw_text:
            raise PipelineError("Bedrock structured output missing text content")

        # Parse the JSON
        try:
            fields = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            raise PipelineError(
                f"Bedrock structured output is not valid JSON: {exc}"
            ) from exc

        if not isinstance(fields, dict):
            raise PipelineError("Bedrock structured output JSON must be an object")
        return fields
