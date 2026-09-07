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


def test_nested_denied_keys_are_redacted_at_any_depth() -> None:
    # A secret nested under an innocent outer key must not leak (Wukong C1).
    nested_secret = "ghp_" + "b" * 32
    payload = _format(
        _record(
            "request context",
            session={"headers": {"Authorization": "Bearer " + "c" * 30}},
            api_payload={"api_key": nested_secret},
            tags=["safe", {"password": "inner-" + "pw"}],
        )
    )
    serialized = json.dumps(payload)
    assert payload["session"]["headers"]["Authorization"] == REDACTED
    assert payload["api_payload"]["api_key"] == REDACTED
    assert payload["tags"][1]["password"] == REDACTED
    assert "c" * 30 not in serialized
    assert nested_secret not in serialized


def test_secret_inside_non_string_object_repr_is_scrubbed() -> None:
    # repr() of arbitrary objects runs AFTER layer 2; the serialized-output
    # pass must still catch pattern families.
    class WeirdObject:
        def __repr__(self) -> str:
            return "WeirdObject(token=sk-" + "z" * 24 + ")"

    payload = _format(_record("weird extra", obj=WeirdObject()))
    assert "sk-" + "z" * 24 not in json.dumps(payload)
    assert REDACTED in str(payload["obj"])


def test_password_only_db_url_is_masked() -> None:
    payload = _format(_record("cache", dsn="redis://:Only" + "Pass123@cache:6379/0"))
    assert "://" + REDACTED + "@" in str(payload["dsn"])
    assert "OnlyPass123" not in json.dumps(payload)


def test_known_secret_containing_json_escaped_chars_is_replaced() -> None:
    # A literal containing a quote is serialized as pa\"ssword; both raw and
    # escaped forms must be replaced.
    tricky_secret = 'pa"ss' + "word"
    record = _record("auth", provider="using " + tricky_secret + " inside")
    formatted = JsonFormatter(service="svc", env="test", known_secrets=(tricky_secret,)).format(
        record
    )
    assert tricky_secret not in formatted
    assert REDACTED in formatted


def test_reserved_payload_keys_are_protected_from_caller_extra() -> None:
    """Caller extra cannot clobber envelope metadata keys."""
    record = _record(
        "legitimate message",
        timestamp="fake-timestamp",
        level="FAKE_LEVEL",
        logger="fake.logger",
        message="fake message clobber",
        service="fake-service",
        env="fake-env",
        request_id="fake-request-id",
        exception={"fake": "exception"},
        legit_extra="preserved-value",
    )
    payload = _format(record)
    assert payload["service"] == "rag-llm-services-api"
    assert payload["env"] == "test"
    assert payload["level"] == "INFO"
    assert payload["logger"] == "tests.observability"
    assert payload["message"] == "legitimate message"
    assert payload["timestamp"] != "fake-timestamp"
    assert payload["timestamp"].endswith("Z")
    assert payload["request_id"] is None  # not set via ContextVar
    assert "exception" not in payload  # record had no exc_info
    assert payload["legit_extra"] == "preserved-value"


def test_short_and_empty_known_secrets_do_not_cause_over_redaction() -> None:
    """Short (< 6 chars) or empty secret strings must not scrub benign output."""
    record = _record("user test_id 12345 processed in test environment")
    payload = _format(
        record,
        known_secrets=("", "1", "12", "123", "1234", "12345", "real-super-secret"),
    )
    # The short values should NOT be redacted wholesale in message or other fields.
    assert "12345" in str(payload["message"])
    assert "test" in str(payload["message"])
    # And empty string must not insert REDACTED between every character.
    assert payload["service"] == "rag-llm-services-api"
    assert payload["env"] == "test"
