"""Security tests for CORS production boundaries."""

from __future__ import annotations

import pytest

from rag_llm_services_api.core.config import Settings
from rag_llm_services_shared.errors import ConfigurationError


def _set_complete_production_env(monkeypatch: pytest.MonkeyPatch) -> None:
    real = "real-value-not-placeholder"
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("LLM_PROVIDER", "deepseek")
    monkeypatch.setenv("QUEUE_PROVIDER", "celery")
    monkeypatch.setenv("RATE_LIMIT_BACKEND", "redis")
    monkeypatch.setenv("DATABASE_URL", f"postgresql+psycopg://u:{real}@db:5432/d")
    monkeypatch.setenv("DEEPSEEK_API_KEY", real)
    monkeypatch.setenv("POSTGRES_PASSWORD", real)
    monkeypatch.setenv("MINIO_ACCESS_KEY", real)
    monkeypatch.setenv("MINIO_SECRET_KEY", real)
    monkeypatch.setenv("N8N_API_KEY", real)
    monkeypatch.setenv("N8N_ENCRYPTION_KEY", real)
    monkeypatch.setenv("GRAFANA_ADMIN_PASSWORD", real)


def test_production_rejects_local_http_cors_origin(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_complete_production_env(monkeypatch)
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:3001")

    with pytest.raises(ConfigurationError) as excinfo:
        Settings(_env_file=None)

    assert "CORS_ORIGINS" in str(excinfo.value)


def test_production_accepts_https_cors_origin(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_complete_production_env(monkeypatch)
    monkeypatch.setenv("CORS_ORIGINS", "https://rag.example.com")

    settings = Settings(_env_file=None)

    assert settings.app.cors_origins == ["https://rag.example.com"]


def test_production_requires_redis_rate_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_complete_production_env(monkeypatch)
    monkeypatch.setenv("CORS_ORIGINS", "https://rag.example.com")
    monkeypatch.setenv("RATE_LIMIT_BACKEND", "memory")

    with pytest.raises(ConfigurationError) as excinfo:
        Settings(_env_file=None)

    assert "RATE_LIMIT_BACKEND" in str(excinfo.value)
