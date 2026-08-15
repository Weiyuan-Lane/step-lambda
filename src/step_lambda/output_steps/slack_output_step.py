import logging
import os
from typing import Any

import httpx

from step_lambda.utils.context import (
    OUTPUT_JIRA,
    OUTPUT_SLACK,
    PROCESSING_BEDROCK,
    PROCESSING_SES_EMAIL,
    Context,
)
from step_lambda.output_steps.output_step import OutputStep

logger = logging.getLogger(__name__)


class SlackOutputStep(OutputStep):
    name = "slack"

    def __init__(self) -> None:
        self._bot_token = os.getenv("SLACK_BOT_TOKEN")
        self._channel = os.getenv("SLACK_CHANNEL")
        raw_handles = os.getenv("SLACK_NOTIFY_HANDLES", "")
        self._notify_handles = [
            part.strip() for part in raw_handles.split(",") if part.strip()
        ]

    def notify(self, context: Context) -> None:
        if not self._bot_token or not self._channel:
            logger.error(
                "SlackOutputStep requires SLACK_BOT_TOKEN and SLACK_CHANNEL; skipping"
            )
            return

        ses_email = context.get(PROCESSING_SES_EMAIL) or {}
        subject = ses_email.get("subject") or "(no subject)"
        bedrock = context.get(PROCESSING_BEDROCK) or {}
        tasks = bedrock.get("tasks") or []
        if not isinstance(tasks, list):
            tasks = []
        jira = context.get(OUTPUT_JIRA) or {}
        jira_url = jira.get("url")
        jira_issue_key = jira.get("issue_key")

        mentions = self._format_mentions(self._notify_handles)
        text = self._fallback_text(subject, tasks, mentions, jira_url, jira_issue_key)
        blocks = self._build_blocks(subject, tasks, mentions, jira_url, jira_issue_key)
        try:
            self._post_api(self._bot_token, self._channel, text, blocks)
        except Exception:
            logger.exception("Failed to post Slack notification; continuing pipeline")
            return

        context.set(OUTPUT_SLACK, {"notified": True})
        logger.info("Posted Slack notification")

    @classmethod
    def _fallback_text(
        cls,
        subject: str,
        tasks: list[Any],
        mentions: str = "",
        jira_url: str | None = None,
        jira_issue_key: str | None = None,
    ) -> str:
        lines = []
        if mentions:
            lines.extend([mentions, ""])
        lines.extend([f"Email received with subject: {subject}", "", "Tasks:"])
        if not tasks:
            lines.append("No tasks detected.")
        else:
            for task in tasks:
                lines.append(f"- {cls._format_task_line(task)}")
        jira_line = cls._format_jira_line(jira_url, jira_issue_key, mrkdwn=False)
        if jira_line:
            lines.extend(["", jira_line])
        return "\n".join(lines)

    @classmethod
    def _build_blocks(
        cls,
        subject: str,
        tasks: list[Any],
        mentions: str = "",
        jira_url: str | None = None,
        jira_issue_key: str | None = None,
    ) -> list[dict[str, Any]]:
        if tasks:
            task_text = "\n".join(f"• {cls._format_task_line(task)}" for task in tasks)
        else:
            task_text = "_No tasks detected._"

        tasks_section = f"*Tasks*\n{task_text}"
        jira_line = cls._format_jira_line(jira_url, jira_issue_key, mrkdwn=True)
        if jira_line:
            tasks_section = f"{tasks_section}\n\n{jira_line}"

        intro = f"*An email was received with subject:*\n{cls._escape_mrkdwn(subject)}"
        if mentions:
            intro = f"{mentions}\n{intro}"

        return [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": intro,
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": tasks_section,
                },
            },
        ]

    @staticmethod
    def _format_jira_line(
        jira_url: str | None,
        jira_issue_key: str | None,
        *,
        mrkdwn: bool,
    ) -> str | None:
        if not jira_url:
            return None
        label = jira_issue_key or "Jira task"
        if mrkdwn:
            return f"*Jira:* <{jira_url}|{label}>"
        return f"Jira: {label} ({jira_url})"

    @staticmethod
    def _format_mentions(handles: list[str]) -> str:
        """Turn comma-list values into Slack mrkdwn mentions.

        Accepts member IDs (U…/W…), usergroup IDs (S…), @handles, or already
        formatted ``<@U…>`` / ``<!subteam^S…>`` tokens.
        """
        mentions: list[str] = []
        for handle in handles:
            if handle.startswith("<") and handle.endswith(">"):
                mentions.append(handle)
            elif handle.startswith(("U", "W")) and handle[1:].isalnum():
                mentions.append(f"<@{handle}>")
            elif handle.startswith("S") and handle[1:].isalnum():
                mentions.append(f"<!subteam^{handle}>")
            elif handle.startswith("@"):
                mentions.append(handle)
            else:
                mentions.append(f"@{handle}")
        return " ".join(mentions)

    @classmethod
    def _format_task_line(cls, task: Any) -> str:
        if not isinstance(task, dict):
            return str(task)

        task_type = task.get("type") or "unknown"
        filename = task.get("filename")
        due = cls._format_process_date(task.get("process_date"))

        label = f"`{task_type}`"
        if filename:
            label = f"{label} (`{filename}`)"
        return f"{label} — by {due}"

    @staticmethod
    def _format_process_date(process_date: Any) -> str:
        if process_date is None:
            return "unknown"
        value = str(process_date).strip()
        if not value or value.lower() == "null":
            return "unknown"
        if value.lower() == "now":
            return "now"
        return value

    @staticmethod
    def _escape_mrkdwn(text: str) -> str:
        return (
            text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )

    @staticmethod
    def _post_api(
        token: str, channel: str, text: str, blocks: list[dict[str, Any]]
    ) -> None:
        with httpx.Client(timeout=30.0) as client:
            response = client.post(
                "https://slack.com/api/chat.postMessage",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "channel": channel,
                    "attachments": [
                        {
                            "color": "#ECB22E",
                            "fallback": text,
                            "blocks": blocks,
                        }
                    ],
                },
            )
            response.raise_for_status()
            data = response.json()
            if not data.get("ok"):
                raise RuntimeError(f"Slack API error: {data.get('error')}")
