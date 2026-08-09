import email
import logging
from email.message import Message
from typing import Any
from urllib.parse import unquote_plus

import boto3

from step_lambda.utils.context import PROCESSING_SES_EMAIL, Context
from step_lambda.utils.errors import PipelineError
from step_lambda.processing_steps.processing_step import ProcessingStep

logger = logging.getLogger(__name__)

class SESEmailProcessingStep(ProcessingStep):
    """Parse an SES → S3 email object into context."""

    name = "ses"

    def __init__(self, s3_client: Any | None = None) -> None:
        self._s3_client = s3_client

    @property
    def _s3(self) -> Any:
        if self._s3_client is None:
            self._s3_client = boto3.client("s3")
        return self._s3_client

    def process(self, event: dict[str, Any], context: Context) -> Context:
        raw_bytes = self._load_email(event)
        parsed = email.message_from_bytes(raw_bytes) if raw_bytes else None

        subject = (parsed["Subject"] if parsed else "") or ""
        from_addr = (parsed["From"] if parsed else "") or ""
        to_header = (parsed.get("To") if parsed else "") or ""
        to_addrs = [a.strip() for a in to_header.split(",") if a.strip()]
        message_id = (parsed["Message-ID"] if parsed else "") or ""
        date = (parsed["Date"] if parsed else "") or ""
        body = self._extract_body(parsed) if parsed else ""
        attachments = self._extract_attachments(parsed)

        email_context = {
            "source": self.name,
            "from": from_addr,
            "to": to_addrs,
            "subject": subject,
            "date": date,
            "body": body,
            "message_id": message_id,
            "attachments": attachments,
            # Primary text for downstream Bedrock (and other) steps.
            "main": f"Subject: {subject}\nDate: {date}\n\n{body}".strip(),
        }
        context.set(PROCESSING_SES_EMAIL, email_context)

        logger.info(
            "SES email parsed message_id=%s from=%s subject=%r attachments=%d context=%r",
            message_id,
            from_addr,
            subject[:80],
            len(attachments),
            email_context,
        )
        return context

    def _load_email(self, event: dict[str, Any]) -> bytes:
        records = event.get("Records") or []
        record = records[0] if records else {}

        if record.get("eventSource") != "aws:s3":
            raise PipelineError(
                f"Expected aws:s3 event; got eventSource={record.get('eventSource')!r}"
            )

        s3_info = record["s3"]
        bucket = s3_info["bucket"]["name"]
        key = unquote_plus(s3_info["object"]["key"])
        obj = self._s3.get_object(Bucket=bucket, Key=key)
        return obj["Body"].read()

    @staticmethod
    def _extract_body(msg: Message) -> str:
        if msg.is_multipart():
            texts: list[str] = []
            for part in msg.walk():
                content_type = part.get_content_type()
                disposition = str(part.get("Content-Disposition") or "")
                if content_type == "text/plain" and "attachment" not in disposition:
                    payload = part.get_payload(decode=True) or b""
                    charset = part.get_content_charset() or "utf-8"
                    texts.append(payload.decode(charset, errors="replace"))
            if texts:
                return "\n".join(texts)
            # Fall back to first text/html part stripped lightly
            for part in msg.walk():
                if part.get_content_type() == "text/html":
                    payload = part.get_payload(decode=True) or b""
                    charset = part.get_content_charset() or "utf-8"
                    return payload.decode(charset, errors="replace")
            return ""

        payload = msg.get_payload(decode=True) or b""
        charset = msg.get_content_charset() or "utf-8"
        return payload.decode(charset, errors="replace")

    @staticmethod
    def _extract_attachments(msg: Message | None) -> list[dict[str, str]]:
        """Return attachment metadata (filename only) from a parsed MIME message."""
        if msg is None:
            return []

        attachments: list[dict[str, str]] = []
        for part in msg.walk():
            if part.get_content_maintype() == "multipart":
                continue
            filename = part.get_filename()
            if not filename:
                continue
            attachments.append({"filename": str(filename)})
        return attachments
