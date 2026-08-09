class PipelineError(Exception):
    """Fail the pipeline and skip remaining steps.

    Use for expected/domain failures (bad input, missing config, rejected
    triage). Unexpected bugs should still raise ordinary exceptions.
    """


class StopPipeline(Exception):
    """Stop remaining steps without treating the run as a failure.

    Use for intentional early exits (e.g. email is not an incident).
    """
