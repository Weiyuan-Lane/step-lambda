from abc import ABC, abstractmethod
from typing import Any

from step_lambda.utils.context import Context

class ProcessingStep(ABC):
    """A unit of work that reads the Lambda event and reads/writes Context, in configured order."""

    name: str = "processing_step"

    @abstractmethod
    def process(self, event: dict[str, Any], context: Context) -> Context:
        """Transform context in place (or return an updated context)."""
