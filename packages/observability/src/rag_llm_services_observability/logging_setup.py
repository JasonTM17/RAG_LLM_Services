"""Structured JSON logging with layered secret redaction.

Redaction layers, each negative-tested:

1. Recursive key denylist over ``extra`` (case-insensitive): a denied key at
   ANY nesting level has its value replaced wholesale; dict, list, tuple, set,
   and frozenset values are traversed.
2. Value-pattern scrub of secret-looking strings (``sk-...``, ``ghp_...``,
   ``Bearer ...``) at every nesting level, in message text, and again on the
   fully serialized output (so ``repr()``/``str()`` fallbacks of arbitrary
   objects cannot smuggle patterns through).
3. Final serialized-output pass replacing any configured ``known_secrets``
   literal (raw and JSON-escaped forms), plus masking of DB-URL credentials
   including password-only URLs.

``configure_logging`` is idempotent: calling it again re-arms a single root
handler instead of stacking duplicates.
"""

from __future__ import annotations

import json
import logging
import re
import sys
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from rag_llm_services_observability.context import get_request_id

REDACTED = "[REDACTED]"

# Layer 1: key denylist matched case-insensitively against extra keys at any
# nesting level.
_SENSITIVE_KEY_PATTERN = re.compile(
    r"api[-_]?key|authorization|password|secret|token|credential|cookie",
    re.IGNORECASE,
)

# Layer 2: secret-looking value patterns (same families as the repo secret scan).
_SECRET_VALUE_PATTERN = re.compile(
    r"sk-[A-Za-z0-9]{20,}|gh[po]_[A-Za-z0-9]{30,}"
    r"|Bearer\s+(sk|gh[po]_)[A-Za-z0-9._\-]{20,}"
)

# Layer 3: DB-URL credentials, e.g. postgresql://user:password@host/db or the
# password-only form redis://:password@host:6379 (empty user is allowed).
_DB_URL_CREDENTIAL_PATTERN = re.compile(r"://[^/@\s]*:[^@/\s]+@")

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


def _redact_mapping(data: Mapping[str, Any]) -> dict[str, Any]:
    redacted: dict[str, Any] = {}
    for key, value in data.items():
        if _SENSITIVE_KEY_PATTERN.search(str(key)):
            redacted[key] = REDACTED
        else:
            redacted[key] = _redact_value(value)
    return redacted


def _redact_value(value: Any) -> Any:
    if isinstance(value, str):
        return _SECRET_VALUE_PATTERN.sub(REDACTED, value)
    if isinstance(value, Mapping):
        return _redact_mapping(value)
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_redact_value(item) for item in value]
    return value


def redact_extra(data: Mapping[str, Any]) -> dict[str, Any]:
    """Redact a logging ``extra`` mapping (layers 1 and 2).

    Denylisted keys at ANY nesting level have their value replaced wholesale;
    container values are traversed recursively; string values get
    secret-looking substrings scrubbed.
    """
    return _redact_mapping(data)


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

        # Server-side traceback: serialized into the log record (never into
        # client responses) and scrubbed like any other free text.
        if record.exc_info:
            exc_type = record.exc_info[0]
            payload["exception"] = {
                "type": exc_type.__name__ if exc_type is not None else "Exception",
                "traceback": redact_text(self.formatException(record.exc_info)),
            }

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
        """Layer 3: scrub the fully serialized output.

        Runs after ``repr()``/``str()`` fallbacks and JSON escaping, so it is
        the backstop for secrets embedded in arbitrary objects (layer 2 runs
        before those conversions) and for configured literals containing
        characters JSON escapes (quotes, backslashes).
        """
        masked = _DB_URL_CREDENTIAL_PATTERN.sub("://[REDACTED]@", serialized)
        for secret in self.known_secrets:
            masked = masked.replace(secret, REDACTED)
            escaped = json.dumps(secret)[1:-1]
            if escaped != secret:
                masked = masked.replace(escaped, REDACTED)
        return _SECRET_VALUE_PATTERN.sub(REDACTED, masked)


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
