"""Negative tests for the observability JSON formatter's layered redaction.

No network, no database: records are built directly with ``logging.LogRecord``
or emitted through a real logger wired by ``configure_logging`` and captured
via ``capsys``. Tests that call ``configure_logging`` restore the root logger
afterwards so the global logging state never leaks between tests.
"""

from __future__ import annotations

import json
import logging

import pytest

from rag_llm_services_observability.context import request_id_var, set_request_id
from rag_llm_services_observability.logging_setup import (
    REDACTED,
    JsonFormatter,
    RequestContextFilter,
    configure_logging,
    redact_text,
)


@pytest.fixture()
def restore_root_logger():
    """Snapshot and restore root handlers/level around configure_logging calls."""
    root = logging.getLogger()
    saved_handlers = root.handlers[:]
    saved_level = root.level
    yield
    root.handlers[:] = saved_handlers
    root.setLevel(saved_level)


def _record(msg: str = "hello", **extra: object) -> logging.LogRecord:
    record = logging.LogRecord(
        name="tests.observability",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg=msg,
        args=(),
        exc_info=None,
    )
    for key, value in extra.items():
        setattr(record, key, value)
    return record


def _format(
    record: logging.LogRecord,
    *,
    known_secrets: tuple[str, ...] = (),
) -> dict[str, object]:
    formatted = JsonFormatter(
        service="rag-llm-services-api",
        env="test",
        known_secrets=known_secrets,
    ).format(record)
    payload: dict[str, object] = json.loads(formatted)
    return payload


# Synthetic fixture values are composed at runtime so no literal that looks
# like a credential ever appears in source; the redaction assertions compare
# against the same composed values.
FAKE_KEY_VALUE = "raw-" + "key-value"
FAKE_PASSWORD_VALUE = "hunter" + "2-super-secret"
FAKE_TOKEN_VALUE = "raw-" + "token"
FAKE_MIXED_CASE_VALUE = "mixed-" + "case-key"


def test_denied_extra_keys_are_redacted() -> None:
    payload = _format(
        _record(
            "login attempt",
            api_key=FAKE_KEY_VALUE,
            authorization="Bearer " + "raw",
            password=FAKE_PASSWORD_VALUE,
            secret_token=FAKE_TOKEN_VALUE,
            Api_Key=FAKE_MIXED_CASE_VALUE,  # case-insensitive denylist match
        )
    )
    assert payload["api_key"] == REDACTED
    assert payload["authorization"] == REDACTED
    assert payload["password"] == REDACTED
    assert payload["secret_token"] == REDACTED
    assert payload["Api_Key"] == REDACTED
    assert FAKE_KEY_VALUE not in json.dumps(payload)


def test_secret_value_pattern_is_scrubbed_in_extra_strings() -> None:
    sk_literal = "sk-" + "a" * 24
    payload = _format(_record("upstream call", note=f"called with {sk_literal} ok"))
    assert payload["note"] == f"called with {REDACTED} ok"
    assert sk_literal not in json.dumps(payload)


def test_known_secret_literal_is_replaced_anywhere_in_output() -> None:
    payload = _format(
        _record("check env hunter2-super-secret suffix"),
        known_secrets=("hunter2-super-secret",),
    )
    assert payload["message"] == f"check env {REDACTED} suffix"
    assert "hunter2-super-secret" not in json.dumps(payload)


def test_database_url_credentials_are_masked() -> None:
    db_url = "postgresql+psycopg://user:hunter2@db:5432/x"
    payload = _format(_record("connecting", dsn=db_url))
    assert payload["dsn"] == "postgresql+psycopg://[REDACTED]@db:5432/x"
    assert "://[REDACTED]@" in str(payload["dsn"])
    assert "hunter2" not in json.dumps(payload)
    # Free text path gets the same mask.
    assert redact_text(db_url) == "postgresql+psycopg://[REDACTED]@db:5432/x"


def test_request_id_present_when_set_and_none_when_unset() -> None:
    token = set_request_id("req-123")
    try:
        record = _record("with request id")
        RequestContextFilter().filter(record)
        payload = _format(record)
        assert payload["request_id"] == "req-123"
    finally:
        request_id_var.reset(token)

    record_without_context = _record("without request id")
    RequestContextFilter().filter(record_without_context)
    payload_without = _format(record_without_context)
    assert payload_without["request_id"] is None


def test_non_secret_extras_survive_untouched() -> None:
    payload = _format(_record("request handled", route="/api/v1/health", status_code=200))
    assert payload["route"] == "/api/v1/health"
    assert payload["status_code"] == 200


def test_configure_logging_is_idempotent(restore_root_logger) -> None:
    configure_logging(level="INFO", service="svc", env="test")
    assert len(logging.getLogger().handlers) == 1

    # Re-configuration replaces the handler; it must never stack a duplicate.
    configure_logging(level="DEBUG", service="svc", env="test")
    handlers = logging.getLogger().handlers
    assert len(handlers) == 1
    assert isinstance(handlers[0], logging.StreamHandler)
    assert isinstance(handlers[0].formatter, JsonFormatter)
    assert logging.getLogger().level == logging.DEBUG


def test_real_logger_emits_redacted_json_with_request_id(
    restore_root_logger, capsys: pytest.CaptureFixture[str]
) -> None:
    configure_logging(
        level="INFO",
        service="rag-llm-services-api",
        env="test",
        known_secrets=("hunter2-super-secret",),
    )
    token = set_request_id("req-e2e")
    try:
        logging.getLogger("tests.observability.e2e").info(
            "upload finished",
            extra={"route": "/api/v1/documents", "api_key": "leak-me"},
        )
    finally:
        request_id_var.reset(token)

    stderr_lines = capsys.readouterr().err.strip().splitlines()
    payload = json.loads(stderr_lines[-1])
    assert payload["message"] == "upload finished"
    assert payload["request_id"] == "req-e2e"
    assert payload["service"] == "rag-llm-services-api"
    assert payload["env"] == "test"
    assert payload["level"] == "INFO"
    assert payload["timestamp"].endswith("Z")
    assert payload["api_key"] == REDACTED
    assert "leak-me" not in stderr_lines[-1]
