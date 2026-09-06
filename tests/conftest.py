"""Shared test fixtures for the RAG LLM Services test suite.

Tests must never read the developer's real ``.env``: settings objects are
always constructed with ``_env_file=None`` and environment input arrives only
through ``monkeypatch.setenv``.
"""

import os

import pytest

from rag_llm_services_api.core.config import get_settings

_SCRUB_PREFIXES = (
    "APP_",
    "API_",
    "CORS_",
    "RAG_",
    "POSTGRES_",
    "DATABASE_",
    "REDIS_",
    "MINIO_",
    "LLM_",
    "DEEPSEEK_",
    "RUN_",
    "EMBEDDING_",
    "RERANKER_",
    "OPENAI_",
    "N8N_",
    "PROMETHEUS_",
    "GRAFANA_",
    "NEXT_PUBLIC_",
    "LOG_LEVEL",
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove app-relevant environment variables so tests see only what they set."""
    for key in list(os.environ):
        if key.startswith(_SCRUB_PREFIXES) or key == "LOG_LEVEL":
            monkeypatch.delenv(key, raising=False)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
