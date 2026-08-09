from typing import Any, TypeVar, overload

T = TypeVar("T")

# Namespaced context keys for step outputs.
PROCESSING_SES_EMAIL = "processing::ses_email"
PROCESSING_BEDROCK = "processing::bedrock"
OUTPUT_JIRA = "output::jira"
OUTPUT_SLACK = "output::slack"


class Context:
    def __init__(self) -> None:
        self._values: dict[str, Any] = {}

    def set(self, key: str, value: Any) -> Context:
        self._values[key] = value
        return self

    @overload
    def get(self, key: str, default: None = None) -> Any | None: ...

    @overload
    def get(self, key: str, default: T) -> T: ...

    def get(self, key: str, default: Any = None) -> Any:
        if key not in self._values:
            return default
        return self._values[key]

    def require(self, key: str) -> Any:
        if key not in self._values:
            raise KeyError(f"Required context key missing: {key!r}")
        return self._values[key]
