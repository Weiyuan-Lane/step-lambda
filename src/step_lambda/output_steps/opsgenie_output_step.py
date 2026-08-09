import logging
import os

import httpx

from step_lambda.utils.context import PROCESSING_SES_EMAIL, Context
from step_lambda.output_steps.output_step import OutputStep

logger = logging.getLogger(__name__)

class OpsgenieOutputStep(OutputStep):
    name = "opsgenie"

    def __init__(self) -> None:
        self._api_key = os.getenv("OPSGENIE_API_KEY")
        self._base_url = (os.getenv("OPSGENIE_API_URL") or "https://api.opsgenie.com").rstrip("/")
        self._priority = os.getenv("OPSGENIE_PRIORITY", "P3") or "P3"

    def notify(self, context: Context) -> None:
        if not self._api_key:
            raise RuntimeError("OpsgenieOutputStep requires OPSGENIE_API_KEY")

        ses_email = context.get(PROCESSING_SES_EMAIL) or {}
        title = context.get("title") or ses_email.get("subject") or "Step Lambda Alert"
        description = context.get("summary") or ses_email.get("main") or "(no body)"
        alias = ses_email.get("message_id") or None

        payload: dict = {
            "message": title[:130],
            "description": description[:15000],
            "priority": self._priority,
            "source": "step-lambda",
            "tags": ["step-lambda", ses_email.get("source") or "unknown"],
        }
        if alias:
            payload["alias"] = alias[:512]

        with httpx.Client(timeout=30.0) as client:
            response = client.post(
                f"{self._base_url}/v2/alerts",
                headers={
                    "Authorization": f"GenieKey {self._api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
            request_id = (data.get("requestId") or data.get("result"))
            context.set("opsgenie_request_id", request_id)
            logger.info("Created Opsgenie alert request_id=%s", request_id)
