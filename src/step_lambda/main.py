import logging
import os
from collections.abc import Callable
from typing import Any

from step_lambda.utils.context import Context
from step_lambda.output_steps.output_step import OutputStep
from step_lambda.output_steps.jira_output_step import JiraOutputStep
from step_lambda.output_steps.opsgenie_output_step import OpsgenieOutputStep
from step_lambda.output_steps.slack_output_step import SlackOutputStep
from step_lambda.processing_steps.processing_step import ProcessingStep
from step_lambda.processing_steps.ses_email_processing_step import SESEmailProcessingStep
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
    BedrockProcessingStep,
]

# Run sequentially after processing completes.
OUTPUT_STEPS: list[Callable[[], OutputStep]] = [
    SlackOutputStep,
    JiraOutputStep,
    OpsgenieOutputStep,
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
    return {
        "ok": True,
        "input": {
            "email": {
                "from": context.get("email_from"),
                "to": context.get("email_to"),
                "subject": context.get("email_subject"),
                "body": context.get("email_body"),
                "message_id": context.get("email_message_id"),
            },
        },
        "metadata": {
            "source": context.get("source"),
            "title": context.get("title"),
            "jira_issue_key": context.get("jira_issue_key"),
            "opsgenie_request_id": context.get("opsgenie_request_id"),
            "slack_notified": context.get("slack_notified", False),
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
    for step in processing_steps:
        logger.info("Running processing step: %s", step.name)
        result = step.process(event, context)
        if result is not None:
            context = result  # type: ignore[assignment]

    # Execute output steps sequentially
    output_steps = output_steps if output_steps is not None else [factory() for factory in OUTPUT_STEPS]
    for output in output_steps:
        logger.info("Running output step: %s", output.name)
        output.notify(context)

    return context
