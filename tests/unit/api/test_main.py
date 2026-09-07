"""Unit tests for FastAPI application setup helpers in main.py."""

from __future__ import annotations

import pytest

from rag_llm_services_api.core.config import Settings
from rag_llm_services_api.main import _collect_known_secrets


def test_collect_known_secrets_ignores_placeholders_and_short_secrets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """_collect_known_secrets filters out placeholders, empty, and <6-char strings."""
    # With default settings, all secrets are placeholders ('replace-with-...'), so none are collected.
    settings_default = Settings(_env_file=None)
    assert _collect_known_secrets(settings_default) == ()

    # Set real secrets, including short ones and empty ones.
    monkeypatch.setenv("POSTGRES_PASSWORD", "short")  # 5 chars -> should be skipped (< 6)
    monkeypatch.setenv("MINIO_ACCESS_KEY", "minio-valid-access-key")  # >= 6 chars -> included
    monkeypatch.setenv("MINIO_SECRET_KEY", "minio-valid-secret-12345")  # >= 6 chars -> included
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-valid-deepseek-key-12345")  # >= 6 chars -> included
    monkeypatch.setenv("N8N_API_KEY", "12345")  # 5 chars -> should be skipped (< 6)
    monkeypatch.setenv("N8N_ENCRYPTION_KEY", "")  # empty -> should be skipped
    monkeypatch.setenv(
        "GRAFANA_ADMIN_PASSWORD", "grafana-password-secure"
    )  # >= 6 chars -> included

    settings_custom = Settings(_env_file=None)
    collected = _collect_known_secrets(settings_custom)

    assert "short" not in collected
    assert "12345" not in collected
    assert "" not in collected
    assert "minio-valid-access-key" in collected
    assert "minio-valid-secret-12345" in collected
    assert "sk-valid-deepseek-key-12345" in collected
    assert "grafana-password-secure" in collected
