"""Shared test fixtures for the RAG LLM Services test suite.

Settings read environment variables only (never ``.env`` in-process), and the
autouse fixture below scrubs every app-relevant environment variable, so the
developer's local environment and `.env` cannot influence test outcomes.
Settings objects additionally use ``_env_file=None`` where constructed
directly, keeping that guardrail explicit even if dotenv support returns.
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
    "QUEUE_",
    "CELERY_",
    "INGESTION_",
    "MINIO_",
    "LLM_",
    "DEEPSEEK_",
    "RUN_",
    "EMBEDDING_",
    "RERANKER_",
    "OPENAI_",
    "N8N_",
    "GENERIC_",
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
