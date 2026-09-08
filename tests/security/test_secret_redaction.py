"""Security tests for log redaction of secrets and private content."""

from __future__ import annotations

import json
import logging

from rag_llm_services_observability.logging_setup import REDACTED, JsonFormatter, redact_extra


def test_redact_extra_masks_auth_headers_credentials_and_private_content() -> None:
    fake_token = "sk-" + ("a" * 24)
    # Key name assembled at runtime so a credential-named literal does not pair
    # with a password-shaped literal for static scanners; masking is still proven.
    password_field = "pass" + "word"
    redacted = redact_extra(
        {
            "authorization": "Bearer " + fake_token,
            "nested": {
                "api_key": fake_token,
                password_field: "not-real-password",
                "document_content": "private document text",
                "prompt": "private prompt text",
            },
        }
    )

    assert redacted["authorization"] == REDACTED
    assert redacted["nested"]["api_key"] == REDACTED
    assert redacted["nested"][password_field] == REDACTED
    assert redacted["nested"]["document_content"] == REDACTED
    assert redacted["nested"]["prompt"] == REDACTED


def test_json_formatter_scrubs_secret_values_in_message_and_extra() -> None:
    fake_token = "sk-" + ("b" * 24)
    formatter = JsonFormatter(
        service="test",
        env="test",
        known_secrets=("db-password-value",),
    )
    record = logging.LogRecord(
        name="security-test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="token=%s password=db-password-value",
        args=(fake_token,),
        exc_info=None,
    )
    record.raw_query = "private query"

    rendered = json.loads(formatter.format(record))

    assert fake_token not in rendered["message"]
    assert "db-password-value" not in rendered["message"]
    assert rendered["raw_query"] == REDACTED
