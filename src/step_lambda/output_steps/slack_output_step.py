import logging
import os

import httpx

from step_lambda.utils.context import PROCESSING_SES_EMAIL, Context
from step_lambda.output_steps.output_step import OutputStep

logger = logging.getLogger(__name__)

class SlackOutputStep(OutputStep):
    name = "slack"

    def __init__(self) -> None:
        self._webhook = os.getenv("SLACK_WEBHOOK_URL")
        self._bot_token = os.getenv("SLACK_BOT_TOKEN")
        self._channel = os.getenv("SLACK_CHANNEL")

    def notify(self, context: Context) -> None:
        ses_email = context.get(PROCESSING_SES_EMAIL) or {}
        title = context.get("title") or ses_email.get("subject") or "Step Lambda Alert"
        summary = context.get("summary") or ses_email.get("main") or "(no body)"
        text = f"*{title}*\n{summary}"

        if self._webhook:
            self._post_webhook(self._webhook, text)
        elif self._bot_token and self._channel:
            self._post_api(self._bot_token, self._channel, text)
        else:
            raise RuntimeError(
                "SlackOutputStep requires SLACK_WEBHOOK_URL or SLACK_BOT_TOKEN + SLACK_CHANNEL"
            )

        context.set("slack_notified", True)
        logger.info("Posted Slack notification")

    @staticmethod
    def _post_webhook(webhook: str, text: str) -> None:
        with httpx.Client(timeout=30.0) as client:
            response = client.post(webhook, json={"text": text})
            response.raise_for_status()

    @staticmethod
    def _post_api(token: str, channel: str, text: str) -> None:
        with httpx.Client(timeout=30.0) as client:
            response = client.post(
                "https://slack.com/api/chat.postMessage",
                headers={"Authorization": f"Bearer {token}"},
                json={"channel": channel, "text": text},
            )
            response.raise_for_status()
            data = response.json()
            if not data.get("ok"):
                raise RuntimeError(f"Slack API error: {data.get('error')}")
