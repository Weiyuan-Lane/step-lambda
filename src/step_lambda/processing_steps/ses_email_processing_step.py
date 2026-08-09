import email
import logging
import os
from email.message import Message
from typing import Any

import boto3

from step_lambda.utils.context import Context
from step_lambda.processing_steps.processing_step import ProcessingStep

logger = logging.getLogger(__name__)

class SESEmailProcessingStep(ProcessingStep):
    """Parse the SES-triggered Lambda event (direct SES or SES → S3) into context."""

    name = "ses"

    def __init__(self, s3_client: Any | None = None) -> None:
        self._s3_client = s3_client

    @property
    def _s3(self) -> Any:
        if self._s3_client is None:
            self._s3_client = boto3.client("s3")
        return self._s3_client

    def process(self, event: dict[str, Any], context: Context) -> Context:
        mail_meta, raw_bytes = self._load_email(event)
        parsed = email.message_from_bytes(raw_bytes) if raw_bytes else None

        subject = mail_meta.get("subject") or (parsed["Subject"] if parsed else "") or ""
        from_addr = mail_meta.get("from") or (parsed["From"] if parsed else "") or ""
        to_addrs = mail_meta.get("to") or []
        if not to_addrs and parsed is not None:
            to_header = parsed.get("To") or ""
            to_addrs = [a.strip() for a in to_header.split(",") if a.strip()]
        message_id = mail_meta.get("messageId") or (parsed["Message-ID"] if parsed else "") or ""
        body = self._extract_body(parsed) if parsed else mail_meta.get("body", "")

        context.set("source", self.name)
        context.set("email_from", from_addr)
        context.set("email_to", to_addrs)
        context.set("email_subject", subject)
        context.set("email_body", body)
        context.set("email_message_id", message_id)
        # Primary text for downstream Bedrock (and other) steps.
        context.set("main", f"Subject: {subject}\n\n{body}".strip())

        logger.info(
            "SES email parsed message_id=%s from=%s subject=%r",
            message_id,
            from_addr,
            subject[:80],
        )
        return context

    def _load_email(self, event: dict[str, Any]) -> tuple[dict[str, Any], bytes]:
        records = event.get("Records") or []
        record = records[0] if records else {}

        # Direct SES invocation
        if record.get("eventSource") == "aws:ses" or "ses" in record:
            ses = record.get("ses") or event.get("ses") or {}
            mail = ses.get("mail") or {}
            meta = {
                "subject": (mail.get("commonHeaders") or {}).get("subject")
                or mail.get("subject"),
                "from": ((mail.get("commonHeaders") or {}).get("from") or [None])[0]
                or (mail.get("source")),
                "to": (mail.get("commonHeaders") or {}).get("to") or mail.get("destination") or [],
                "messageId": mail.get("messageId"),
            }
            raw = self._fetch_from_s3_by_message_id(meta.get("messageId"))
            return meta, raw

        # S3 object created by SES receipt rule
        if record.get("eventSource") == "aws:s3":
            s3_info = record["s3"]
            bucket = s3_info["bucket"]["name"]
            key = s3_info["object"]["key"]
            obj = self._s3.get_object(Bucket=bucket, Key=key)
            raw = obj["Body"].read()
            return {}, raw

        return {}, b""

    def _fetch_from_s3_by_message_id(self, message_id: str | None) -> bytes:
        bucket = os.getenv("SES_EMAIL_BUCKET")
        prefix = os.getenv("SES_EMAIL_PREFIX", "incoming/")
        if not bucket or not message_id:
            logger.warning(
                "SES email body unavailable (bucket=%r message_id=%r); "
                "headers-only context will be used",
                bucket,
                message_id,
            )
            return b""
        key = f"{prefix}{message_id}"
        try:
            obj = self._s3.get_object(Bucket=bucket, Key=key)
            return obj["Body"].read()
        except Exception:
            logger.exception("Failed to fetch SES email s3://%s/%s", bucket, key)
            return b""

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
