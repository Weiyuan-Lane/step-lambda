from abc import ABC, abstractmethod

from step_lambda.utils.context import Context

class OutputStep(ABC):
    """Notifier that sends a side-effect based on the final Context."""

    name: str = "output"

    @abstractmethod
    def notify(self, context: Context) -> None:
        """Deliver a notification using context values from earlier stages."""
