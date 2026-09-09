"""Settings tests: .env.example parity, fail-fast production guard, drivers.

Tests never read the developer's real ``.env``: every Settings is constructed
with ``_env_file=None`` and environment input arrives only through
``monkeypatch.setenv`` (the shared autouse fixture scrubs app variables).
"""

from pathlib import Path

import pytest
from pydantic import ValidationError

from rag_llm_services_api.core.config import KNOWN_ENV_VARS, PLACEHOLDER_MARKERS, Settings
from rag_llm_services_shared.errors import ConfigurationError

REPO_ROOT = Path(__file__).resolve().parents[3]
ENV_EXAMPLE = REPO_ROOT / ".env.example"


def _env_example_keys() -> set[str]:
    keys: set[str] = set()
    for line in ENV_EXAMPLE.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        keys.add(stripped.split("=", 1)[0].strip())
    return keys


def test_env_example_parity_both_directions() -> None:
    file_keys = _env_example_keys()
    missing_from_known = sorted(file_keys - set(KNOWN_ENV_VARS))
    extra_in_known = sorted(set(KNOWN_ENV_VARS) - file_keys)
    assert not missing_from_known, f"keys missing from KNOWN_ENV_VARS: {missing_from_known}"
    assert not extra_in_known, f"KNOWN_ENV_VARS keys absent from .env.example: {extra_in_known}"


def test_local_defaults_construct(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings(_env_file=None)
    assert settings.app.env == "local"
    assert settings.app.api_port == 8000
    assert settings.llm.provider == "fake"
    assert settings.deepseek.base_url == "https://api.deepseek.com"
    assert settings.deepseek.model == "deepseek-v4-flash"
    assert settings.deepseek.api_mode == "responses"
    assert settings.deepseek.max_retries == 2
    assert settings.deepseek.run_live_tests is False
    assert settings.rag.vector_top_k == 10
    assert settings.rag.keyword_top_k == 10
    assert settings.rag.rerank_top_k == 8
    assert settings.rag.rrf_k == 60
    assert settings.rag.rrf_vector_weight == 1.0
    assert settings.rag.rrf_keyword_weight == 1.0
    assert settings.agents.tool_max_results == 5
    assert settings.agents.tool_max_context_chunks == 5
    assert settings.agents.tool_max_chunk_chars == 1200
    assert settings.agents.tool_max_context_chars == 6000
    assert settings.agents.tool_max_documents == 20
    assert settings.agents.history_max_messages == 8
    assert settings.agents.history_max_chars == 12000
    assert settings.queue.provider == "memory"
    assert settings.queue.celery_broker_url == "redis://redis:6379/1"
    assert settings.queue.ingestion_queue_name == "ingestion"
    assert settings.queue.ingestion_task_max_retries == 3
    assert settings.queue.visibility_timeout_seconds == 3600
    assert settings.queue.worker_pool == "threads"
    assert settings.queue.worker_concurrency == 4
    assert settings.rate_limit.enabled is True
    assert settings.rate_limit.backend == "memory"
    assert settings.rate_limit.requests_per_window == 120
    assert settings.rate_limit.window_seconds == 60
    assert settings.n8n.host == "localhost"
    assert settings.n8n.image == "docker.n8n.io/n8nio/n8n:2.37.11"
    assert settings.n8n.port == 5678
    assert settings.n8n.protocol == "http"
    assert settings.n8n.webhook_url == "http://localhost:5678/"
    assert settings.n8n.metrics is True
    assert settings.n8n.metrics_include_default_metrics is True
    assert settings.n8n.metrics_include_queue_metrics is True
    assert settings.n8n.notification_webhook_url is None
    assert settings.n8n.generic_timezone == "Asia/Bangkok"
    assert settings.n8n.rag_api_base_url == "http://host.docker.internal:8000/api/v1"
    assert settings.observability.worker_metrics_enabled is False
    assert settings.observability.worker_metrics_host == "0.0.0.0"
    assert settings.observability.worker_metrics_port == 9108
    assert settings.observability.worker_metrics_host_port == 9108
    assert settings.observability.prometheus_image == "prom/prometheus:v2.55.1"
    assert settings.observability.prometheus_port == 9090
    assert settings.observability.prometheus_retention_time == "15d"
    assert (
        settings.observability.postgres_exporter_image
        == "quay.io/prometheuscommunity/postgres-exporter:v0.15.0"
    )
    assert settings.observability.postgres_exporter_port == 9187
    assert settings.observability.redis_exporter_image == "oliver006/redis_exporter:v1.62.0"
    assert settings.observability.redis_exporter_port == 9121
    assert settings.observability.cadvisor_image == "gcr.io/cadvisor/cadvisor:v0.49.1"
    assert settings.observability.cadvisor_port == 8080
    assert settings.observability.grafana_image == "grafana/grafana:13.2.1"
    assert settings.observability.grafana_port == 3000
    assert settings.evaluation.dataset_path == "evals/datasets/baseline-learning-rag.jsonl"
    assert settings.evaluation.reports_dir == "evals/reports/local"
    assert settings.evaluation.top_k == 5
    assert settings.evaluation.retrieval_hit_rate_threshold == 1.0
    assert settings.evaluation.recall_at_k_threshold == 0.8
    assert settings.evaluation.mrr_threshold == 0.8
    assert settings.evaluation.ndcg_at_k_threshold == 0.8
    assert settings.evaluation.context_relevance_threshold == 0.5
    assert settings.evaluation.answer_relevance_threshold == 0.65
    assert settings.evaluation.citation_correctness_threshold == 1.0
    assert settings.evaluation.citation_recall_threshold == 0.8
    assert settings.evaluation.faithfulness_threshold == 0.6
    assert settings.frontend.web_port == 3001
    assert settings.frontend.rag_backend_origin == "http://localhost:8000"


def test_retrieval_defaults_are_configurable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RAG_VECTOR_TOP_K", "12")
    monkeypatch.setenv("RAG_KEYWORD_TOP_K", "7")
    monkeypatch.setenv("RAG_RERANK_TOP_K", "5")
    monkeypatch.setenv("RAG_RRF_K", "42")
    monkeypatch.setenv("RAG_RRF_VECTOR_WEIGHT", "1.5")
    monkeypatch.setenv("RAG_RRF_KEYWORD_WEIGHT", "0.7")

    settings = Settings(_env_file=None)

    assert settings.rag.vector_top_k == 12
    assert settings.rag.keyword_top_k == 7
    assert settings.rag.rerank_top_k == 5
    assert settings.rag.rrf_k == 42
    assert settings.rag.rrf_vector_weight == 1.5
    assert settings.rag.rrf_keyword_weight == 0.7


def test_worker_pool_rejects_prefork_for_in_process_metrics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("WORKER_POOL", "prefork")

    with pytest.raises(ValidationError, match="WORKER_POOL"):
        Settings(_env_file=None)


def test_production_with_placeholder_secret_raises_and_hides_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    with pytest.raises(ConfigurationError) as excinfo:
        Settings(_env_file=None)
    message = str(excinfo.value)
    assert "DEEPSEEK_API_KEY" in message
    for marker in PLACEHOLDER_MARKERS:
        assert marker not in message


def test_production_with_dev_auth_enabled_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("LLM_PROVIDER", "deepseek")
    monkeypatch.setenv("QUEUE_PROVIDER", "celery")
    monkeypatch.setenv("CORS_ORIGINS", "https://rag.example.com")
    monkeypatch.setenv("RATE_LIMIT_BACKEND", "redis")
    real = "real-value-not-a-placeholder"
    monkeypatch.setenv("DATABASE_URL", f"postgresql+psycopg://u:{real}@db:5432/d")
    monkeypatch.setenv("DEEPSEEK_API_KEY", real)
    monkeypatch.setenv("POSTGRES_PASSWORD", real)
    monkeypatch.setenv("MINIO_ACCESS_KEY", real)
    monkeypatch.setenv("MINIO_SECRET_KEY", real)
    monkeypatch.setenv("N8N_API_KEY", real)
    monkeypatch.setenv("N8N_ENCRYPTION_KEY", real)
    monkeypatch.setenv("GRAFANA_ADMIN_PASSWORD", real)
    monkeypatch.setenv("RAG_DEV_AUTH_ENABLED", "true")
    with pytest.raises(ConfigurationError) as excinfo:
        Settings(_env_file=None)
    assert "dev auth" in str(excinfo.value)


def test_production_with_complete_config_constructs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("LLM_PROVIDER", "deepseek")
    monkeypatch.setenv("QUEUE_PROVIDER", "celery")
    monkeypatch.setenv("CORS_ORIGINS", "https://rag.example.com")
    monkeypatch.setenv("RATE_LIMIT_BACKEND", "redis")
    real = "real-value-not-a-placeholder"
    monkeypatch.setenv("DATABASE_URL", f"postgresql+psycopg://u:{real}@db:5432/d")
    monkeypatch.setenv("DEEPSEEK_API_KEY", real)
    monkeypatch.setenv("POSTGRES_PASSWORD", real)
    monkeypatch.setenv("MINIO_ACCESS_KEY", real)
    monkeypatch.setenv("MINIO_SECRET_KEY", real)
    monkeypatch.setenv("N8N_API_KEY", real)
    monkeypatch.setenv("N8N_ENCRYPTION_KEY", real)
    monkeypatch.setenv("GRAFANA_ADMIN_PASSWORD", real)
    monkeypatch.setenv("RAG_AUTH_JWT_SECRET", "0" * 32)
    settings = Settings(_env_file=None)
    assert settings.app.env == "production"
    assert settings.dev_auth.auth_enabled is False


def test_database_url_rewrites_to_psycopg_driver(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@db:5432/d")
    settings = Settings(_env_file=None)
    assert settings.database.url.startswith("postgresql+psycopg://")


def test_database_url_rejects_other_drivers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "mysql://u:p@db:3306/d")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_deepseek_base_url_rejects_v1_suffix(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
    with pytest.raises(ValidationError) as excinfo:
        Settings(_env_file=None)
    # Our validator's message text must be present (pydantic appends the
    # developer-supplied input value to its own report, which is not a secret).
    assert "must not include the /v1 path suffix" in str(excinfo.value)


def test_deepseek_base_url_strips_trailing_slash(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/")
    settings = Settings(_env_file=None)
    assert settings.deepseek.base_url == "https://api.deepseek.com"


def test_cors_origins_parses_comma_separated(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CORS_ORIGINS", "http://a.com, http://b.com")
    settings = Settings(_env_file=None)
    assert settings.app.cors_origins == ["http://a.com", "http://b.com"]


def test_cors_origins_reject_wildcard(monkeypatch: pytest.MonkeyPatch) -> None:
    # Credentials are enabled, so a wildcard origin must fail validation.
    monkeypatch.setenv("CORS_ORIGINS", "*")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_production_guard_covers_every_required_var(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Behavioral pin against guard drift: each documented required variable,
    # missing one at a time, must be named by the production guard.
    from rag_llm_services_api.core.config import PRODUCTION_REQUIRED_SECRET_VARS

    real = "real-value-not-a-placeholder"
    complete = {
        "DATABASE_URL": f"postgresql+psycopg://u:{real}@db:5432/d",
        "DEEPSEEK_API_KEY": real,
        "POSTGRES_PASSWORD": real,
        "MINIO_ACCESS_KEY": real,
        "MINIO_SECRET_KEY": real,
        "N8N_API_KEY": real,
        "N8N_ENCRYPTION_KEY": real,
        "GRAFANA_ADMIN_PASSWORD": real,
        "RAG_AUTH_JWT_SECRET": "0" * 32,
    }
    assert set(complete) == set(PRODUCTION_REQUIRED_SECRET_VARS)
    for missing in PRODUCTION_REQUIRED_SECRET_VARS:
        # Remove the probe variable: earlier iterations may have set it.
        monkeypatch.delenv(missing, raising=False)
        for key, value in complete.items():
            if key == missing:
                continue
            monkeypatch.setenv(key, value)
        monkeypatch.setenv("LLM_PROVIDER", "deepseek")
        monkeypatch.setenv("QUEUE_PROVIDER", "celery")
        monkeypatch.setenv("CORS_ORIGINS", "https://rag.example.com")
        monkeypatch.setenv("RATE_LIMIT_BACKEND", "redis")
        monkeypatch.setenv("APP_ENV", "production")
        with pytest.raises(ConfigurationError) as excinfo:
            Settings(_env_file=None)
        assert missing in str(excinfo.value)


def test_production_requires_celery_queue(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("LLM_PROVIDER", "deepseek")
    monkeypatch.setenv("QUEUE_PROVIDER", "memory")
    monkeypatch.setenv("CORS_ORIGINS", "https://rag.example.com")
    monkeypatch.setenv("RATE_LIMIT_BACKEND", "redis")
    real = "real-value-not-a-placeholder"
    monkeypatch.setenv("DATABASE_URL", f"postgresql+psycopg://u:{real}@db:5432/d")
    monkeypatch.setenv("DEEPSEEK_API_KEY", real)
    monkeypatch.setenv("POSTGRES_PASSWORD", real)
    monkeypatch.setenv("MINIO_ACCESS_KEY", real)
    monkeypatch.setenv("MINIO_SECRET_KEY", real)
    monkeypatch.setenv("N8N_API_KEY", real)
    monkeypatch.setenv("N8N_ENCRYPTION_KEY", real)
    monkeypatch.setenv("GRAFANA_ADMIN_PASSWORD", real)

    with pytest.raises(ConfigurationError) as excinfo:
        Settings(_env_file=None)

    assert "QUEUE_PROVIDER" in str(excinfo.value)
