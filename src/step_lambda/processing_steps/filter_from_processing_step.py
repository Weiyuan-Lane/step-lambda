import logging
import os
from email.utils import parseaddr
from typing import Any

from step_lambda.utils.context import PROCESSING_SES_EMAIL, Context
from step_lambda.utils.errors import PipelineError, StopPipeline
from step_lambda.processing_steps.processing_step import ProcessingStep

logger = logging.getLogger(__name__)


class FilterFromProcessingStep(ProcessingStep):
    """Allowlist the SES From address; stop the pipeline when it does not match."""

    name = "filter_from"

    def __init__(self, allowed_from_addresses: list[str] | None = None) -> None:
        if allowed_from_addresses is None:
            raw = os.getenv("FILTER_FROM_EMAILS", "")
            allowed_from_addresses = [part.strip() for part in raw.split(",") if part.strip()]
        self._allowed_from_addresses = {addr.lower() for addr in allowed_from_addresses}

    def process(self, event: dict[str, Any], context: Context) -> Context:
        if not self._allowed_from_addresses:
            logger.warning(
                "FILTER_FROM_EMAILS is empty; FilterFromProcessingStep allows all senders"
            )
            return context

        ses_email = context.get(PROCESSING_SES_EMAIL) or {}
        from_header = ses_email.get("from") or ""
        from_addr = self._normalize_address(from_header)

        if not from_addr:
            raise PipelineError("From address is missing")

        if from_addr not in self._allowed_from_addresses:
            raise StopPipeline(
                f"From address {from_addr!r} is not in FILTER_FROM_EMAILS"
            )

        logger.info("From address allowed: %s", from_addr)
        return context

    @staticmethod
    def _normalize_address(value: str) -> str:
        _, addr = parseaddr(value)
        return (addr or value).strip().lower()
