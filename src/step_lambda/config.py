import json
import logging
import os
import time
from typing import Any

import boto3
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

_SECRETS_TTL_SECONDS = 10 * 60

_secrets_client = None
_secret_cache: dict[str, Any] | None = None
_secret_loaded_at: float = 0.0

def _client():
    global _secrets_client
    if _secrets_client is None:
        _secrets_client = boto3.client("secretsmanager")
    return _secrets_client

def _secret_cache_expired() -> bool:
    if _secret_cache is None:
        return True
    return (time.monotonic() - _secret_loaded_at) >= _SECRETS_TTL_SECONDS

def load_environment() -> None:
    """Load .env for local runs, then overlay Secrets Manager values in production."""
    load_dotenv(override=False)

    if os.getenv("ENVIRONMENT") != "production":
        logger.info("ENVIRONMENT is not production; skipping Secrets Manager")
        return

    load_from_secrets_manager()

def load_from_secrets_manager() -> None:
    """Fetch JSON secret from Secrets Manager and merge into the process environment.

    Reuses a cached payload for up to 10 minutes so warm Lambda invocations avoid
    calling Secrets Manager on every request, while still picking up rotations.
    """
    global _secret_cache, _secret_loaded_at

    secret_arn = os.getenv("SECRETS_MANAGER_ARN") or os.getenv("SECRETS_MANAGER_SECRET_ID")
    if not secret_arn:
        logger.info("No SECRETS_MANAGER_ARN set; using process env / .env only")
        return

    if _secret_cache_expired():
        try:
            response = _client().get_secret_value(SecretId=secret_arn)
            raw = response.get("SecretString") or ""
            if not raw and "SecretBinary" in response:
                raw = response["SecretBinary"].decode("utf-8")
            data = json.loads(raw)
            if not isinstance(data, dict):
                raise ValueError(f"Secret {secret_arn!r} must be a JSON object")
            _secret_cache = data
            _secret_loaded_at = time.monotonic()
        except Exception:
            logger.exception("Failed to load secret %s", secret_arn)
            raise

    for key, value in _secret_cache.items():
        if value is None:
            continue
        os.environ[key] = str(value) if not isinstance(value, (dict, list)) else json.dumps(value)
