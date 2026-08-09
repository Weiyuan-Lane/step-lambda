import logging
import os

import httpx

from step_lambda.utils.context import Context
from step_lambda.output_steps.output_step import OutputStep

logger = logging.getLogger(__name__)

class OpsgenieOutputStep(OutputStep):
    name = "opsgenie"

    def notify(self, context: Context) -> None:
        api_key = os.getenv("OPSGENIE_API_KEY")
        base_url = (os.getenv("OPSGENIE_API_URL") or "https://api.opsgenie.com").rstrip("/")
        priority = os.getenv("OPSGENIE_PRIORITY", "P3") or "P3"

        if not api_key:
            raise RuntimeError("OpsgenieOutputStep requires OPSGENIE_API_KEY")

        title = context.get("title") or context.get("email_subject") or "Step Lambda Alert"
        description = context.get("summary") or context.get("main") or "(no body)"
        alias = context.get("email_message_id") or None

        payload: dict = {
            "message": title[:130],
            "description": description[:15000],
            "priority": priority,
            "source": "step-lambda",
            "tags": ["step-lambda", context.get("source") or "unknown"],
        }
        if alias:
            payload["alias"] = alias[:512]

        with httpx.Client(timeout=30.0) as client:
            response = client.post(
                f"{base_url}/v2/alerts",
                headers={
                    "Authorization": f"GenieKey {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
            request_id = (data.get("requestId") or data.get("result"))
            context.set("opsgenie_request_id", request_id)
            logger.info("Created Opsgenie alert request_id=%s", request_id)
