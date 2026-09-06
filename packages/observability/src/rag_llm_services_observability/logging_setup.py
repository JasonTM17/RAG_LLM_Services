"""Structured JSON logging with layered secret redaction.

Three redaction layers, each negative-tested:

1. Key denylist on ``extra`` values (case-insensitive).
2. Value-pattern scrub of secret-looking strings (``sk-...``, ``ghp_...``,
   ``Bearer ...``) in message text and string extra values.
3. Final serialized-output pass replacing any configured ``known_secrets``
   literal, plus masking of DB-URL credentials.

``configure_logging`` is idempotent: calling it again re-arms a single root
handler instead of stacking duplicates.
"""

from __future__ import annotations

import json
import logging
import re
import sys
from datetime import UTC, datetime
from typing import Any

from rag_llm_services_observability.context import get_request_id

REDACTED = "[REDACTED]"

# Layer 1: key denylist matched case-insensitively against extra keys.
_SENSITIVE_KEY_PATTERN = re.compile(
    r"api[-_]?key|authorization|password|secret|token|credential|cookie",
    re.IGNORECASE,
)

# Layer 2: secret-looking value patterns (same families as the repo secret scan).
_SECRET_VALUE_PATTERN = re.compile(
    r"sk-[A-Za-z0-9]{20,}|gh[po]_[A-Za-z0-9]{30,}"
    r"|Bearer\s+(sk|gh[po]_)[A-Za-z0-9._\-]{20,}"
)

# Layer 3: DB-URL credentials, e.g. postgresql://user:password@host/db.
_DB_URL_CREDENTIAL_PATTERN = re.compile(r"://[^:/@\s]+:[^@/\s]+@")

# Standard LogRecord attributes, excluded explicitly when merging ``extra``
# into the JSON payload so only genuine caller extras reach the top level.
# Includes "message"/"asctime" which logging adds during formatting.
_STANDARD_LOGRECORD_ATTRS = frozenset(
    {
        "name",
        "msg",
        "args",
        "levelname",
        "levelno",
        "pathname",
        "filename",
        "module",
        "exc_info",
        "exc_text",
        "stack_info",
        "lineno",
        "funcName",
        "created",
        "msecs",
        "relativeCreated",
        "thread",
        "threadName",
        "processName",
        "process",
        "taskName",
        "message",
        "asctime",
    }
)


def redact_extra(data: dict[str, Any]) -> dict[str, Any]:
    """Redact a logging ``extra`` mapping (layers 1 and 2).

    Denylisted keys have their value replaced wholesale; other string values
    get secret-looking substrings scrubbed.
    """
    redacted: dict[str, Any] = {}
    for key, value in data.items():
        if _SENSITIVE_KEY_PATTERN.search(str(key)):
            redacted[key] = REDACTED
        elif isinstance(value, str):
            redacted[key] = _SECRET_VALUE_PATTERN.sub(REDACTED, value)
        else:
            redacted[key] = value
    return redacted


def redact_text(text: str) -> str:
    """Scrub secret-looking substrings and DB-URL credentials from free text."""
    scrubbed = _SECRET_VALUE_PATTERN.sub(REDACTED, text)
    return _DB_URL_CREDENTIAL_PATTERN.sub("://[REDACTED]@", scrubbed)


class RequestContextFilter(logging.Filter):
    """Inject the current request ID onto every record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id()
        return True


class JsonFormatter(logging.Formatter):
    """Serialize records as one-line JSON documents with redaction applied."""

    def __init__(
        self,
        *,
        service: str,
        env: str,
        known_secrets: tuple[str, ...] = (),
    ) -> None:
        super().__init__()
        self.service = service
        self.env = env
        self.known_secrets = tuple(secret for secret in known_secrets if secret)

    def format(self, record: logging.LogRecord) -> str:
        if "request_id" in record.__dict__:
            request_id = record.__dict__["request_id"]
        else:
            request_id = get_request_id()

        payload: dict[str, Any] = {
            "timestamp": self._format_timestamp(record.created),
            "level": record.levelname,
            "logger": record.name,
            "message": redact_text(record.getMessage()),
            "service": self.service,
            "env": self.env,
            "request_id": request_id,
        }

        # request_id is emitted above; skip it here so it never appears twice.
        extra = {
            key: value
            for key, value in record.__dict__.items()
            if key not in _STANDARD_LOGRECORD_ATTRS and key != "request_id"
        }
        payload.update(redact_extra(extra))

        # json.dumps must never raise: non-serializable values fall back to repr.
        serialized = json.dumps(payload, default=self._json_default)
        return self._final_pass(serialized)

    @staticmethod
    def _format_timestamp(created: float) -> str:
        return datetime.fromtimestamp(created, tz=UTC).isoformat().replace("+00:00", "Z")

    @staticmethod
    def _json_default(value: Any) -> str:
        try:
            return repr(value)
        except Exception:  # noqa: BLE001, pragma: no cover - repr() failing is pathological
            return f"<unrepr-able {type(value).__name__}>"

    def _final_pass(self, serialized: str) -> str:
        """Layer 3: mask DB credentials and configured secrets in the output."""
        masked = _DB_URL_CREDENTIAL_PATTERN.sub("://[REDACTED]@", serialized)
        for secret in self.known_secrets:
            if secret in masked:
                masked = masked.replace(secret, REDACTED)
        return masked


def configure_logging(
    *,
    level: str = "INFO",
    service: str,
    env: str,
    known_secrets: tuple[str, ...] = (),
) -> None:
    """Install the JSON root handler exactly once (idempotent).

    Removes any existing root handlers first so repeated calls (tests,
    lifespan restarts, worker re-entry) never duplicate log lines.
    """
    root = logging.getLogger()
    for existing in list(root.handlers):
        root.removeHandler(existing)

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(JsonFormatter(service=service, env=env, known_secrets=known_secrets))
    handler.addFilter(RequestContextFilter())
    root.addHandler(handler)
    root.setLevel(level.upper())
