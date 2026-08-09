import logging
import os
from typing import Any

import httpx

from step_lambda.utils.context import (
    OUTPUT_JIRA,
    PROCESSING_BEDROCK,
    PROCESSING_SES_EMAIL,
    Context,
)
from step_lambda.output_steps.output_step import OutputStep

logger = logging.getLogger(__name__)

_ISSUE_TYPE = "Task"


class JiraOutputStep(OutputStep):
    name = "jira"

    def __init__(self) -> None:
        self._base_url = (os.getenv("JIRA_BASE_URL") or "").rstrip("/")
        self._email = os.getenv("JIRA_EMAIL")
        self._api_token = os.getenv("JIRA_API_TOKEN")
        self._project_key = os.getenv("JIRA_PROJECT_KEY")
        self._assignee_account_id = os.getenv("JIRA_ASSIGNEE_ACCOUNT_ID")

    def notify(self, context: Context) -> None:
        if not all(
            [
                self._base_url,
                self._email,
                self._api_token,
                self._project_key,
                self._assignee_account_id,
            ]
        ):
            raise RuntimeError(
                "JiraOutputStep requires JIRA_BASE_URL, JIRA_EMAIL, JIRA_API_TOKEN, "
                "JIRA_PROJECT_KEY, JIRA_ASSIGNEE_ACCOUNT_ID"
            )

        bedrock = context.get(PROCESSING_BEDROCK) or {}
        tasks = bedrock.get("tasks") or []
        if not isinstance(tasks, list):
            tasks = []
        if not tasks:
            logger.info("No tasks in context; skipping Jira issue creation")
            return

        ses_email = context.get(PROCESSING_SES_EMAIL) or {}
        subject = ses_email.get("subject") or "(no subject)"
        summary = f"Email tasks — {subject}"[:255]

        payload = {
            "fields": {
                "project": {"key": self._project_key},
                "summary": summary,
                "description": self._build_description(ses_email, tasks),
                "issuetype": {"name": _ISSUE_TYPE},
                "assignee": {"accountId": self._assignee_account_id},
            }
        }

        url = f"{self._base_url}/rest/api/3/issue"
        with httpx.Client(timeout=30.0) as client:
            response = client.post(
                url,
                json=payload,
                auth=(self._email, self._api_token),
                headers={"Accept": "application/json", "Content-Type": "application/json"},
            )
            response.raise_for_status()
            data = response.json()
            issue_key = data.get("key")
            issue_url = f"{self._base_url}/browse/{issue_key}" if issue_key else None
            context.set(
                OUTPUT_JIRA,
                {"issue_key": issue_key, "url": issue_url},
            )
            logger.info("Created Jira issue %s (%s)", issue_key, issue_url)

    @classmethod
    def _build_description(
        cls, ses_email: dict[str, Any], tasks: list[Any]
    ) -> dict[str, Any]:
        from_addr = ses_email.get("from") or "(unknown)"
        date = ses_email.get("date") or "(unknown)"
        subject = ses_email.get("subject") or "(no subject)"

        content: list[dict[str, Any]] = [
            cls._paragraph_with_label("Subject", subject),
            cls._paragraph_with_label("From", from_addr),
            cls._paragraph_with_label("Date", date),
            {
                "type": "paragraph",
                "content": [
                    {"type": "text", "text": "Tasks", "marks": [{"type": "strong"}]}
                ],
            },
            {
                "type": "bulletList",
                "content": [
                    {
                        "type": "listItem",
                        "content": [
                            {
                                "type": "paragraph",
                                "content": [
                                    {
                                        "type": "text",
                                        "text": cls._format_task_line(task),
                                    }
                                ],
                            }
                        ],
                    }
                    for task in tasks
                ],
            },
        ]
        return {"type": "doc", "version": 1, "content": content}

    @staticmethod
    def _paragraph_with_label(label: str, value: str) -> dict[str, Any]:
        return {
            "type": "paragraph",
            "content": [
                {"type": "text", "text": f"{label}: ", "marks": [{"type": "strong"}]},
                {"type": "text", "text": value[:10000]},
            ],
        }

    @classmethod
    def _format_task_line(cls, task: Any) -> str:
        if not isinstance(task, dict):
            return str(task)

        task_type = task.get("type") or "unknown"
        filename = task.get("filename")
        due = cls._format_process_date(task.get("process_date"))

        label = task_type
        if filename:
            label = f"{label} ({filename})"
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
