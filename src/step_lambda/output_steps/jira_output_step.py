import logging
import os

import httpx

from step_lambda.utils.context import Context
from step_lambda.output_steps.output_step import OutputStep

logger = logging.getLogger(__name__)

class JiraOutputStep(OutputStep):
    name = "jira"

    def notify(self, context: Context) -> None:
        base_url = (os.getenv("JIRA_BASE_URL") or "").rstrip("/")
        email = os.getenv("JIRA_EMAIL")
        api_token = os.getenv("JIRA_API_TOKEN")
        project_key = os.getenv("JIRA_PROJECT_KEY")
        issue_type = os.getenv("JIRA_ISSUE_TYPE", "Task") or "Task"

        if not all([base_url, email, api_token, project_key]):
            raise RuntimeError(
                "JiraOutputStep requires JIRA_BASE_URL, JIRA_EMAIL, JIRA_API_TOKEN, JIRA_PROJECT_KEY"
            )

        title = context.get("title") or context.get("email_subject") or "Step Lambda Alert"
        description = context.get("summary") or context.get("main") or "(no body)"

        payload = {
            "fields": {
                "project": {"key": project_key},
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
                "issuetype": {"name": issue_type},
            }
        }

        url = f"{base_url}/rest/api/3/issue"
        with httpx.Client(timeout=30.0) as client:
            response = client.post(
                url,
                json=payload,
                auth=(email, api_token),
                headers={"Accept": "application/json", "Content-Type": "application/json"},
            )
            response.raise_for_status()
            data = response.json()
            issue_key = data.get("key")
            context.set("jira_issue_key", issue_key)
            logger.info("Created Jira issue %s", issue_key)
