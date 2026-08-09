import logging
import os
from collections.abc import Callable
from typing import Any

from step_lambda.utils.context import (
    OUTPUT_JIRA,
    OUTPUT_SLACK,
    PROCESSING_SES_EMAIL,
    Context,
)
from step_lambda.utils.errors import PipelineError, StopPipeline
from step_lambda.output_steps.output_step import OutputStep
from step_lambda.output_steps.jira_output_step import JiraOutputStep
from step_lambda.output_steps.slack_output_step import SlackOutputStep
from step_lambda.processing_steps.processing_step import ProcessingStep
from step_lambda.processing_steps.ses_email_processing_step import SESEmailProcessingStep
from step_lambda.processing_steps.filter_from_processing_step import FilterFromProcessingStep
from step_lambda.processing_steps.bedrock_processing_step import BedrockProcessingStep
from step_lambda.config import load_environment

logger = logging.getLogger(__name__)
if not logging.getLogger().handlers:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
# ---------------------------------------------------------------------------
# Pipeline configuration — edit order / membership here. --------------------
# ---------------------------------------------------------------------------

# Run sequentially; earlier steps can populate context for later ones.
PROCESSING_STEPS: list[Callable[[], ProcessingStep]] = [
    SESEmailProcessingStep,
    FilterFromProcessingStep,
    BedrockProcessingStep,
]

# Run sequentially after processing completes.
OUTPUT_STEPS: list[Callable[[], OutputStep]] = [
    JiraOutputStep,
    SlackOutputStep,
]

# ---------------------------------------------------------------------------
# end pipeline configuration ------------------------------------------------
# ---------------------------------------------------------------------------

# Main entrypoint for AWS Lambda
def handler(event: dict[str, Any], lambda_context: Any = None) -> dict[str, Any]:
    """AWS Lambda handler."""
    load_environment()
    logger.info("Handler invoked request_id=%s", getattr(lambda_context, "aws_request_id", None))
    context = run_pipeline(event)
    ses_email = context.get(PROCESSING_SES_EMAIL) or {}
    jira = context.get(OUTPUT_JIRA) or {}
    slack = context.get(OUTPUT_SLACK) or {}
    status = context.get("pipeline_status", "ok")
    return {
        "ok": status != "error",
        "status": status,
        "message": context.get("pipeline_message"),
        "input": {
            "email": {
                "from": ses_email.get("from"),
                "to": ses_email.get("to"),
                "subject": ses_email.get("subject"),
                "body": ses_email.get("body"),
                "message_id": ses_email.get("message_id"),
                "attachments": ses_email.get("attachments") or [],
            },
        },
        "metadata": {
            "jira_issue_key": jira.get("issue_key"),
            "jira_url": jira.get("url"),
            "slack_notified": bool(slack.get("notified")),
        },
    }

# Run configured stages in order: processing → outputs.
def run_pipeline(
    event: dict[str, Any],
    *,
    processing_steps: list[ProcessingStep] | None = None,
    output_steps: list[OutputStep] | None = None,
) -> Context:
    """Execute the configured pipeline against a Lambda event."""

    context = Context()

    # Execute processing steps sequentially
    processing_steps = (
        processing_steps if processing_steps is not None else [factory() for factory in PROCESSING_STEPS]
    )
    output_steps = output_steps if output_steps is not None else [factory() for factory in OUTPUT_STEPS]

    try:
        for step in processing_steps:
            logger.info("Running processing step: %s", step.name)
            result = step.process(event, context)
            if result is not None:
                context = result  # type: ignore[assignment]

        for output in output_steps:
            logger.info("Running output step: %s", output.name)
            output.notify(context)
    except StopPipeline as exc:
        logger.info("Pipeline stopped early: %s", exc)
        context.set("pipeline_status", "stopped")
        context.set("pipeline_message", str(exc) or None)
    except PipelineError as exc:
        logger.error("Pipeline failed: %s", exc)
        context.set("pipeline_status", "error")
        context.set("pipeline_message", str(exc) or None)
    else:
        context.set("pipeline_status", "ok")

    return context
