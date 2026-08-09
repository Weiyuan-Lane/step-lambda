import logging
import os

import httpx

from step_lambda.utils.context import PROCESSING_SES_EMAIL, Context
from step_lambda.output_steps.output_step import OutputStep

logger = logging.getLogger(__name__)

class JiraOutputStep(OutputStep):
    name = "jira"

    def __init__(self) -> None:
        self._base_url = (os.getenv("JIRA_BASE_URL") or "").rstrip("/")
        self._email = os.getenv("JIRA_EMAIL")
        self._api_token = os.getenv("JIRA_API_TOKEN")
        self._project_key = os.getenv("JIRA_PROJECT_KEY")
        self._issue_type = os.getenv("JIRA_ISSUE_TYPE", "Task") or "Task"

    def notify(self, context: Context) -> None:
        if not all([self._base_url, self._email, self._api_token, self._project_key]):
            raise RuntimeError(
                "JiraOutputStep requires JIRA_BASE_URL, JIRA_EMAIL, JIRA_API_TOKEN, JIRA_PROJECT_KEY"
            )

        ses_email = context.get(PROCESSING_SES_EMAIL) or {}
        title = context.get("title") or ses_email.get("subject") or "Step Lambda Alert"
        description = context.get("summary") or ses_email.get("main") or "(no body)"

        payload = {
            "fields": {
                "project": {"key": self._project_key},
                "summary": title[:255],
                "description": {
                    "type": "doc",
                    "version": 1,
                    "content": [
                        {
                            "type": "paragraph",
                            "content": [{"type": "text", "text": description[:30000]}],
                        }
                    ],
                },
                "issuetype": {"name": self._issue_type},
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
            context.set("jira_issue_key", issue_key)
            logger.info("Created Jira issue %s", issue_key)
