"""Typed application settings with fail-fast production validation.

Contract notes:

- Every in-process field maps to exactly one ``.env.example`` key through an
  explicit full-name ``validation_alias``; ``KNOWN_ENV_VARS`` and
  ``.env.example`` must stay in parity, including compose/frontend-only keys
  enforced by ``tests/unit/api/test_config.py``.
- ``local``/``development``/``test`` environments get development defaults so
  the app and tests run offline; ``production`` fails fast with safe errors
  when mandatory configuration is missing or still a placeholder, and dev
  auth must be disabled (fail closed, per the operating appendix).
- Error messages name the offending field only and never echo configured
  values, URLs, or placeholder material.
"""

from collections.abc import Callable
from functools import lru_cache
from typing import Annotated
from uuid import UUID

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from rag_llm_services_api.core.security import validate_cors_origins_for_environment
from rag_llm_services_shared.errors import ConfigurationError

PLACEHOLDER_MARKERS = ("replace-with", "changeme", "your-", "example")

PRODUCTION_REQUIRED_SECRET_VARS = (
    "DATABASE_URL",
    "DEEPSEEK_API_KEY",
    "POSTGRES_PASSWORD",
    "MINIO_ACCESS_KEY",
    "MINIO_SECRET_KEY",
    "N8N_API_KEY",
    "N8N_ENCRYPTION_KEY",
    "GRAFANA_ADMIN_PASSWORD",
)

# Keep in parity with .env.example (enforced in both directions by tests).
KNOWN_ENV_VARS = frozenset(
    {
        "APP_ENV",
        "LOG_LEVEL",
        "API_HOST",
        "API_PORT",
        "CORS_ORIGINS",
        "RAG_DEV_AUTH_ENABLED",
        "RAG_DEV_USER_ID",
        "POSTGRES_DB",
        "POSTGRES_USER",
        "POSTGRES_PASSWORD",
        "DATABASE_URL",
        "REDIS_URL",
        "RATE_LIMIT_ENABLED",
        "RATE_LIMIT_BACKEND",
        "RATE_LIMIT_REQUESTS_PER_WINDOW",
        "RATE_LIMIT_WINDOW_SECONDS",
        "QUEUE_PROVIDER",
        "CELERY_BROKER_URL",
        "CELERY_RESULT_BACKEND",
        "INGESTION_QUEUE_NAME",
        "INGESTION_TASK_MAX_RETRIES",
        "INGESTION_TASK_RETRY_BACKOFF_SECONDS",
        "INGESTION_TASK_RETRY_BACKOFF_MAX_SECONDS",
        "INGESTION_TASK_RETRY_JITTER",
        "INGESTION_JOB_STALE_AFTER_SECONDS",
        "QUEUE_VISIBILITY_TIMEOUT_SECONDS",
        "RETRIEVAL_CACHE_TTL_SECONDS",
        "WORKER_POOL",
        "WORKER_CONCURRENCY",
        "MINIO_ENDPOINT",
        "MINIO_ACCESS_KEY",
        "MINIO_SECRET_KEY",
        "MINIO_BUCKET",
        "LLM_PROVIDER",
        "DEEPSEEK_API_KEY",
        "DEEPSEEK_BASE_URL",
        "DEEPSEEK_MODEL",
        "DEEPSEEK_API_MODE",
        "DEEPSEEK_ALLOW_CHAT_COMPLETIONS_FALLBACK",
        "DEEPSEEK_FALLBACK_REASON",
        "DEEPSEEK_MAX_RETRIES",
        "DEEPSEEK_RETRY_BACKOFF_SECONDS",
        "DEEPSEEK_ESTIMATED_INPUT_CACHE_MISS_USD_PER_1M",
        "DEEPSEEK_ESTIMATED_INPUT_CACHE_HIT_USD_PER_1M",
        "DEEPSEEK_ESTIMATED_OUTPUT_USD_PER_1M",
        "RUN_DEEPSEEK_LIVE_TESTS",
        "LLM_MAX_INPUT_TOKENS",
        "LLM_MAX_OUTPUT_TOKENS",
        "LLM_DAILY_ESTIMATED_COST_LIMIT_USD",
        "LLM_REQUEST_TIMEOUT_SECONDS",
        "RAG_CONTEXT_TOKEN_BUDGET",
        "RAG_VECTOR_TOP_K",
        "RAG_KEYWORD_TOP_K",
        "RAG_RERANK_TOP_K",
        "RAG_RRF_K",
        "RAG_RRF_VECTOR_WEIGHT",
        "RAG_RRF_KEYWORD_WEIGHT",
        "EMBEDDING_PROVIDER",
        "EMBEDDING_MODEL",
        "RERANKER_PROVIDER",
        "RERANKER_MODEL",
        "OPENAI_TRACING_DISABLED",
        "AGENT_TOOL_MAX_RESULTS",
        "AGENT_TOOL_MAX_CONTEXT_CHUNKS",
        "AGENT_TOOL_MAX_CHUNK_CHARS",
        "AGENT_TOOL_MAX_CONTEXT_CHARS",
        "AGENT_TOOL_MAX_DOCUMENTS",
        "AGENT_HISTORY_MAX_MESSAGES",
        "AGENT_HISTORY_MAX_CHARS",
        "N8N_BASE_URL",
        "N8N_IMAGE",
        "N8N_HOST",
        "N8N_PORT",
        "N8N_PROTOCOL",
        "N8N_WEBHOOK_URL",
        "N8N_METRICS",
        "N8N_METRICS_INCLUDE_DEFAULT_METRICS",
        "N8N_METRICS_INCLUDE_QUEUE_METRICS",
        "N8N_API_KEY",
        "N8N_ENCRYPTION_KEY",
        "N8N_NOTIFICATION_WEBHOOK_URL",
        "N8N_STUDY_TOPIC",
        "GENERIC_TIMEZONE",
        "RAG_API_BASE_URL",
        "RAG_WORKFLOW_OWNER_ID",
        "WORKER_METRICS_ENABLED",
        "WORKER_METRICS_HOST",
        "WORKER_METRICS_PORT",
        "WORKER_METRICS_HOST_PORT",
        "PROMETHEUS_IMAGE",
        "PROMETHEUS_BASE_URL",
        "PROMETHEUS_PORT",
        "PROMETHEUS_RETENTION_TIME",
        "POSTGRES_EXPORTER_IMAGE",
        "POSTGRES_EXPORTER_PORT",
        "REDIS_EXPORTER_IMAGE",
        "REDIS_EXPORTER_PORT",
        "CADVISOR_IMAGE",
        "CADVISOR_PORT",
        "GRAFANA_IMAGE",
        "GRAFANA_PORT",
        "GRAFANA_BASE_URL",
        "GRAFANA_ADMIN_USER",
        "GRAFANA_ADMIN_PASSWORD",
        "EVAL_DATASET_PATH",
        "EVAL_REPORTS_DIR",
        "EVAL_TOP_K",
        "EVAL_RETRIEVAL_HIT_RATE_THRESHOLD",
        "EVAL_RECALL_AT_K_THRESHOLD",
        "EVAL_MRR_THRESHOLD",
        "EVAL_NDCG_AT_K_THRESHOLD",
        "EVAL_CONTEXT_RELEVANCE_THRESHOLD",
        "EVAL_ANSWER_RELEVANCE_THRESHOLD",
        "EVAL_CITATION_CORRECTNESS_THRESHOLD",
        "EVAL_CITATION_RECALL_THRESHOLD",
        "EVAL_FAITHFULNESS_THRESHOLD",
        "EVAL_RUN_STALE_AFTER_SECONDS",
        "WEB_PORT",
        "RAG_BACKEND_ORIGIN",
    }
)


def _settings_factory[SettingsModelT: BaseSettings](
    settings_type: type[SettingsModelT],
) -> Callable[[], SettingsModelT]:
    """Build a default factory for Pydantic settings models.

    BaseSettings constructors are intentionally dynamic: defaults and env
    aliases are resolved at runtime. Mypy cannot model that constructor shape
    without a plugin, so this helper keeps the dynamic boundary in one place.
    """

    def factory() -> SettingsModelT:
        return settings_type()  # type: ignore[call-arg]

    return factory


class AppSettings(BaseSettings):
    """Application identity, logging, and HTTP server surface."""

    model_config = SettingsConfigDict(extra="ignore")

    env: str = Field("local", validation_alias="APP_ENV")
    log_level: str = Field("INFO", validation_alias="LOG_LEVEL")
    api_host: str = Field("0.0.0.0", validation_alias="API_HOST")
    api_port: int = Field(8000, validation_alias="API_PORT")
    # NoDecode: CORS_ORIGINS is a comma-separated string, not JSON; the
    # validator below performs the split.
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:3000"], validation_alias="CORS_ORIGINS"
    )

    @field_validator("env")
    @classmethod
    def _check_env(cls, value: str) -> str:
        allowed = {"local", "development", "test", "production"}
        if value not in allowed:
            raise ValueError("APP_ENV must be one of: local, development, test, production")
        return value

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_cors(cls, value: object) -> object:
        if isinstance(value, str):
            return [part.strip() for part in value.split(",") if part.strip()]
        return value

    @field_validator("cors_origins")
    @classmethod
    def _reject_wildcard_with_credentials(cls, value: list[str]) -> list[str]:
        # CORSMiddleware runs with allow_credentials=True, so a wildcard
        # origin would send credentials to any site.
        if "*" in value:
            raise ValueError("CORS_ORIGINS must not contain '*' (credentials are enabled)")
        return value

    @model_validator(mode="after")
    def _validate_cors_for_environment(self) -> "AppSettings":
        self.cors_origins = validate_cors_origins_for_environment(self.cors_origins, "development")
        return self


class DevAuthSettings(BaseSettings):
    """Local-only principal resolution; production must fail closed."""

    model_config = SettingsConfigDict(extra="ignore")

    auth_enabled: bool = Field(False, validation_alias="RAG_DEV_AUTH_ENABLED")
    user_id: UUID | None = Field(None, validation_alias="RAG_DEV_USER_ID")


class PostgresSettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    db: str = Field("rag_llm_services", validation_alias="POSTGRES_DB")
    user: str = Field("rag_app", validation_alias="POSTGRES_USER")
    password: str = Field("replace-with-local-password", validation_alias="POSTGRES_PASSWORD")


class DatabaseSettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    url: str = Field(
        "postgresql+psycopg://rag_app:replace-with-local-password@postgres:5432/rag_llm_services",
        validation_alias="DATABASE_URL",
    )

    @field_validator("url")
    @classmethod
    def _require_psycopg_driver(cls, value: str) -> str:
        normalized = value.strip()
        if normalized.startswith("postgresql://"):
            normalized = normalized.replace("postgresql://", "postgresql+psycopg://", 1)
        elif normalized.startswith("postgres://"):
            normalized = normalized.replace("postgres://", "postgresql+psycopg://", 1)
        if not normalized.startswith("postgresql+psycopg://"):
            raise ValueError("DATABASE_URL must use the postgresql+psycopg:// driver (psycopg 3)")
        return normalized


class RedisSettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    url: str = Field("redis://redis:6379/0", validation_alias="REDIS_URL")


class RateLimitSettings(BaseSettings):
    """Request rate-limit settings for browser and API clients."""

    model_config = SettingsConfigDict(extra="ignore")

    enabled: bool = Field(True, validation_alias="RATE_LIMIT_ENABLED")
    backend: str = Field("memory", validation_alias="RATE_LIMIT_BACKEND")
    requests_per_window: int = Field(
        120, ge=1, le=100_000, validation_alias="RATE_LIMIT_REQUESTS_PER_WINDOW"
    )
    window_seconds: int = Field(60, ge=1, le=86_400, validation_alias="RATE_LIMIT_WINDOW_SECONDS")

    @field_validator("backend")
    @classmethod
    def _check_backend(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"memory", "redis"}:
            raise ValueError("RATE_LIMIT_BACKEND must be one of: memory, redis")
        return normalized


class QueueSettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    provider: str = Field("memory", validation_alias="QUEUE_PROVIDER")
    celery_broker_url: str = Field("redis://redis:6379/1", validation_alias="CELERY_BROKER_URL")
    celery_result_backend: str = Field(
        "redis://redis:6379/2", validation_alias="CELERY_RESULT_BACKEND"
    )
    ingestion_queue_name: str = Field("ingestion", validation_alias="INGESTION_QUEUE_NAME")
    ingestion_task_max_retries: int = Field(
        3, ge=0, le=10, validation_alias="INGESTION_TASK_MAX_RETRIES"
    )
    ingestion_task_retry_backoff_seconds: int = Field(
        5, ge=1, le=3600, validation_alias="INGESTION_TASK_RETRY_BACKOFF_SECONDS"
    )
    ingestion_task_retry_backoff_max_seconds: int = Field(
        300, ge=1, le=86400, validation_alias="INGESTION_TASK_RETRY_BACKOFF_MAX_SECONDS"
    )
    ingestion_task_retry_jitter: bool = Field(True, validation_alias="INGESTION_TASK_RETRY_JITTER")
    ingestion_job_stale_after_seconds: int = Field(
        3600, ge=60, le=86400, validation_alias="INGESTION_JOB_STALE_AFTER_SECONDS"
    )
    visibility_timeout_seconds: int = Field(
        3600, ge=60, le=86400, validation_alias="QUEUE_VISIBILITY_TIMEOUT_SECONDS"
    )
    retrieval_cache_ttl_seconds: int = Field(
        300, ge=0, le=86400, validation_alias="RETRIEVAL_CACHE_TTL_SECONDS"
    )
    worker_pool: str = Field("threads", validation_alias="WORKER_POOL")
    worker_concurrency: int = Field(4, ge=1, le=64, validation_alias="WORKER_CONCURRENCY")

    @field_validator("provider")
    @classmethod
    def _check_provider(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"memory", "celery"}:
            raise ValueError("QUEUE_PROVIDER must be one of: memory, celery")
        return normalized

    @field_validator("ingestion_queue_name")
    @classmethod
    def _check_queue_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized or not all(ch.isalnum() or ch in {"-", "_"} for ch in normalized):
            raise ValueError("INGESTION_QUEUE_NAME must contain only letters, numbers, '-' or '_'")
        return normalized

    @field_validator("worker_pool")
    @classmethod
    def _check_worker_pool(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"threads", "solo"}:
            raise ValueError("WORKER_POOL must be one of: threads, solo")
        return normalized


class MinioSettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    endpoint: str = Field("http://minio:9000", validation_alias="MINIO_ENDPOINT")
    access_key: str = Field(
        "replace-with-local-minio-access-key", validation_alias="MINIO_ACCESS_KEY"
    )
    secret_key: str = Field("replace-with-local-minio-secret", validation_alias="MINIO_SECRET_KEY")
    bucket: str = Field("rag-documents", validation_alias="MINIO_BUCKET")


class LlmSettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    provider: str = Field("fake", validation_alias="LLM_PROVIDER")
    max_input_tokens: int = Field(12000, validation_alias="LLM_MAX_INPUT_TOKENS")
    max_output_tokens: int = Field(2048, validation_alias="LLM_MAX_OUTPUT_TOKENS")
    daily_estimated_cost_limit_usd: float = Field(
        5.0, validation_alias="LLM_DAILY_ESTIMATED_COST_LIMIT_USD"
    )
    request_timeout_seconds: int = Field(60, validation_alias="LLM_REQUEST_TIMEOUT_SECONDS")

    @field_validator("provider")
    @classmethod
    def _check_provider(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"fake", "deepseek"}:
            raise ValueError("LLM_PROVIDER must be one of: fake, deepseek")
        return normalized


class DeepseekSettings(BaseSettings):
    """Provider configuration only; the gateway itself arrives in Phase 06."""

    model_config = SettingsConfigDict(extra="ignore")

    api_key: str = Field("replace-with-your-deepseek-api-key", validation_alias="DEEPSEEK_API_KEY")
    base_url: str = Field("https://api.deepseek.com", validation_alias="DEEPSEEK_BASE_URL")
    model: str = Field("deepseek-v4-flash", validation_alias="DEEPSEEK_MODEL")
    api_mode: str = Field("responses", validation_alias="DEEPSEEK_API_MODE")
    allow_chat_completions_fallback: bool = Field(
        False, validation_alias="DEEPSEEK_ALLOW_CHAT_COMPLETIONS_FALLBACK"
    )
    fallback_reason: str | None = Field(None, validation_alias="DEEPSEEK_FALLBACK_REASON")
    max_retries: int = Field(2, ge=0, le=5, validation_alias="DEEPSEEK_MAX_RETRIES")
    retry_backoff_seconds: float = Field(
        0.25, ge=0.0, le=10.0, validation_alias="DEEPSEEK_RETRY_BACKOFF_SECONDS"
    )
    estimated_input_cache_miss_usd_per_1m: float = Field(
        0.0, ge=0.0, validation_alias="DEEPSEEK_ESTIMATED_INPUT_CACHE_MISS_USD_PER_1M"
    )
    estimated_input_cache_hit_usd_per_1m: float = Field(
        0.0, ge=0.0, validation_alias="DEEPSEEK_ESTIMATED_INPUT_CACHE_HIT_USD_PER_1M"
    )
    estimated_output_usd_per_1m: float = Field(
        0.0, ge=0.0, validation_alias="DEEPSEEK_ESTIMATED_OUTPUT_USD_PER_1M"
    )
    run_live_tests: bool = Field(False, validation_alias="RUN_DEEPSEEK_LIVE_TESTS")

    @field_validator("base_url")
    @classmethod
    def _forbid_v1_suffix(cls, value: str) -> str:
        normalized = value.strip().rstrip("/")
        if normalized.endswith("/v1"):
            raise ValueError("DEEPSEEK_BASE_URL must not include the /v1 path suffix")
        return normalized

    @field_validator("api_mode")
    @classmethod
    def _check_api_mode(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"responses", "chat_completions"}:
            raise ValueError("DEEPSEEK_API_MODE must be one of: responses, chat_completions")
        return normalized

    @field_validator("fallback_reason")
    @classmethod
    def _normalize_fallback_reason(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            return None
        if len(normalized) > 240:
            raise ValueError("DEEPSEEK_FALLBACK_REASON must be 240 characters or fewer")
        return normalized

    @model_validator(mode="after")
    def _fallback_requires_reason(self) -> "DeepseekSettings":
        fallback_selected = self.api_mode == "chat_completions"
        if fallback_selected and not self.allow_chat_completions_fallback:
            raise ValueError(
                "DEEPSEEK_ALLOW_CHAT_COMPLETIONS_FALLBACK must be true for chat_completions mode"
            )
        if self.allow_chat_completions_fallback and not self.fallback_reason:
            raise ValueError(
                "DEEPSEEK_FALLBACK_REASON is required when Chat Completions fallback is enabled"
            )
        return self


class RagSettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    context_token_budget: int = Field(6000, validation_alias="RAG_CONTEXT_TOKEN_BUDGET")
    vector_top_k: int = Field(10, ge=1, le=100, validation_alias="RAG_VECTOR_TOP_K")
    keyword_top_k: int = Field(10, ge=1, le=100, validation_alias="RAG_KEYWORD_TOP_K")
    rerank_top_k: int = Field(8, ge=1, le=50, validation_alias="RAG_RERANK_TOP_K")
    rrf_k: int = Field(60, ge=1, validation_alias="RAG_RRF_K")
    rrf_vector_weight: float = Field(1.0, ge=0.0, validation_alias="RAG_RRF_VECTOR_WEIGHT")
    rrf_keyword_weight: float = Field(1.0, ge=0.0, validation_alias="RAG_RRF_KEYWORD_WEIGHT")


class EmbeddingSettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    provider: str = Field("bge-m3", validation_alias="EMBEDDING_PROVIDER")
    model: str = Field("BAAI/bge-m3", validation_alias="EMBEDDING_MODEL")
    reranker_provider: str = Field("bge", validation_alias="RERANKER_PROVIDER")
    reranker_model: str = Field("BAAI/bge-reranker-v2-m3", validation_alias="RERANKER_MODEL")


class OpenaiAgentsSettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    tracing_disabled: bool = Field(True, validation_alias="OPENAI_TRACING_DISABLED")
    tool_max_results: int = Field(5, ge=1, le=20, validation_alias="AGENT_TOOL_MAX_RESULTS")
    tool_max_context_chunks: int = Field(
        5, ge=1, le=20, validation_alias="AGENT_TOOL_MAX_CONTEXT_CHUNKS"
    )
    tool_max_chunk_chars: int = Field(
        1200, ge=200, le=4000, validation_alias="AGENT_TOOL_MAX_CHUNK_CHARS"
    )
    tool_max_context_chars: int = Field(
        6000, ge=1000, le=24000, validation_alias="AGENT_TOOL_MAX_CONTEXT_CHARS"
    )
    tool_max_documents: int = Field(20, ge=1, le=100, validation_alias="AGENT_TOOL_MAX_DOCUMENTS")
    history_max_messages: int = Field(8, ge=1, le=50, validation_alias="AGENT_HISTORY_MAX_MESSAGES")
    history_max_chars: int = Field(
        12000, ge=1000, le=50000, validation_alias="AGENT_HISTORY_MAX_CHARS"
    )


class N8nSettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    base_url: str = Field("http://n8n:5678", validation_alias="N8N_BASE_URL")
    image: str = Field("docker.n8n.io/n8nio/n8n:2.37.11", validation_alias="N8N_IMAGE")
    host: str = Field("localhost", validation_alias="N8N_HOST")
    port: int = Field(5678, ge=1, le=65535, validation_alias="N8N_PORT")
    protocol: str = Field("http", validation_alias="N8N_PROTOCOL")
    webhook_url: str = Field("http://localhost:5678/", validation_alias="N8N_WEBHOOK_URL")
    metrics: bool = Field(True, validation_alias="N8N_METRICS")
    metrics_include_default_metrics: bool = Field(
        True, validation_alias="N8N_METRICS_INCLUDE_DEFAULT_METRICS"
    )
    metrics_include_queue_metrics: bool = Field(
        True, validation_alias="N8N_METRICS_INCLUDE_QUEUE_METRICS"
    )
    api_key: str = Field("replace-with-local-n8n-api-key", validation_alias="N8N_API_KEY")
    encryption_key: str = Field(
        "replace-with-local-n8n-encryption-key", validation_alias="N8N_ENCRYPTION_KEY"
    )
    notification_webhook_url: str | None = Field(
        None, validation_alias="N8N_NOTIFICATION_WEBHOOK_URL"
    )
    study_topic: str = Field("RAG fundamentals", validation_alias="N8N_STUDY_TOPIC")
    generic_timezone: str = Field("Asia/Bangkok", validation_alias="GENERIC_TIMEZONE")
    rag_api_base_url: str = Field(
        "http://host.docker.internal:8000/api/v1",
        validation_alias="RAG_API_BASE_URL",
    )
    workflow_owner_id: UUID = Field(
        UUID("00000000-0000-0000-0000-000000000001"),
        validation_alias="RAG_WORKFLOW_OWNER_ID",
    )

    @field_validator("protocol")
    @classmethod
    def _check_protocol(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"http", "https"}:
            raise ValueError("N8N_PROTOCOL must be one of: http, https")
        return normalized


class ObservabilitySettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    worker_metrics_enabled: bool = Field(False, validation_alias="WORKER_METRICS_ENABLED")
    worker_metrics_host: str = Field("0.0.0.0", validation_alias="WORKER_METRICS_HOST")
    worker_metrics_port: int = Field(9108, ge=1, le=65535, validation_alias="WORKER_METRICS_PORT")
    worker_metrics_host_port: int = Field(
        9108, ge=1, le=65535, validation_alias="WORKER_METRICS_HOST_PORT"
    )
    prometheus_image: str = Field("prom/prometheus:v2.55.1", validation_alias="PROMETHEUS_IMAGE")
    prometheus_base_url: str = Field(
        "http://prometheus:9090", validation_alias="PROMETHEUS_BASE_URL"
    )
    prometheus_port: int = Field(9090, ge=1, le=65535, validation_alias="PROMETHEUS_PORT")
    prometheus_retention_time: str = Field("15d", validation_alias="PROMETHEUS_RETENTION_TIME")
    postgres_exporter_image: str = Field(
        "quay.io/prometheuscommunity/postgres-exporter:v0.15.0",
        validation_alias="POSTGRES_EXPORTER_IMAGE",
    )
    postgres_exporter_port: int = Field(
        9187, ge=1, le=65535, validation_alias="POSTGRES_EXPORTER_PORT"
    )
    redis_exporter_image: str = Field(
        "oliver006/redis_exporter:v1.62.0", validation_alias="REDIS_EXPORTER_IMAGE"
    )
    redis_exporter_port: int = Field(9121, ge=1, le=65535, validation_alias="REDIS_EXPORTER_PORT")
    cadvisor_image: str = Field(
        "gcr.io/cadvisor/cadvisor:v0.49.1", validation_alias="CADVISOR_IMAGE"
    )
    cadvisor_port: int = Field(8080, ge=1, le=65535, validation_alias="CADVISOR_PORT")
    grafana_image: str = Field("grafana/grafana:13.2.1", validation_alias="GRAFANA_IMAGE")
    grafana_port: int = Field(3000, ge=1, le=65535, validation_alias="GRAFANA_PORT")
    grafana_base_url: str = Field("http://grafana:3000", validation_alias="GRAFANA_BASE_URL")
    grafana_admin_user: str = Field("admin", validation_alias="GRAFANA_ADMIN_USER")
    grafana_admin_password: str = Field(
        "replace-with-local-grafana-password", validation_alias="GRAFANA_ADMIN_PASSWORD"
    )


class EvaluationSettings(BaseSettings):
    """Deterministic RAG evaluation defaults and regression thresholds."""

    model_config = SettingsConfigDict(extra="ignore")

    dataset_path: str = Field(
        "evals/datasets/baseline-learning-rag.jsonl",
        validation_alias="EVAL_DATASET_PATH",
    )
    reports_dir: str = Field("evals/reports/local", validation_alias="EVAL_REPORTS_DIR")
    top_k: int = Field(5, ge=1, le=100, validation_alias="EVAL_TOP_K")
    retrieval_hit_rate_threshold: float = Field(
        1.0, ge=0.0, le=1.0, validation_alias="EVAL_RETRIEVAL_HIT_RATE_THRESHOLD"
    )
    recall_at_k_threshold: float = Field(
        0.8, ge=0.0, le=1.0, validation_alias="EVAL_RECALL_AT_K_THRESHOLD"
    )
    mrr_threshold: float = Field(0.8, ge=0.0, le=1.0, validation_alias="EVAL_MRR_THRESHOLD")
    ndcg_at_k_threshold: float = Field(
        0.8, ge=0.0, le=1.0, validation_alias="EVAL_NDCG_AT_K_THRESHOLD"
    )
    context_relevance_threshold: float = Field(
        0.5, ge=0.0, le=1.0, validation_alias="EVAL_CONTEXT_RELEVANCE_THRESHOLD"
    )
    answer_relevance_threshold: float = Field(
        0.65, ge=0.0, le=1.0, validation_alias="EVAL_ANSWER_RELEVANCE_THRESHOLD"
    )
    citation_correctness_threshold: float = Field(
        1.0, ge=0.0, le=1.0, validation_alias="EVAL_CITATION_CORRECTNESS_THRESHOLD"
    )
    citation_recall_threshold: float = Field(
        0.8, ge=0.0, le=1.0, validation_alias="EVAL_CITATION_RECALL_THRESHOLD"
    )
    faithfulness_threshold: float = Field(
        0.6, ge=0.0, le=1.0, validation_alias="EVAL_FAITHFULNESS_THRESHOLD"
    )
    run_stale_after_seconds: int = Field(
        3600, ge=60, le=86400, validation_alias="EVAL_RUN_STALE_AFTER_SECONDS"
    )


class FrontendSettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    web_port: int = Field(3001, ge=1, le=65535, validation_alias="WEB_PORT")
    rag_backend_origin: str = Field("http://localhost:8000", validation_alias="RAG_BACKEND_ORIGIN")


class Settings(BaseSettings):
    """Root settings object aggregating every configuration domain.

    Environment variables are the single in-process configuration source:
    ``.env`` files are loaded by the runtime instead (``uvicorn --env-file``,
    ``docker compose env_file``), which keeps the process hermetic in tests
    and avoids dotenv sources that cannot cascade into nested models.
    """

    model_config = SettingsConfigDict(extra="ignore")

    app: AppSettings = Field(default_factory=_settings_factory(AppSettings))
    dev_auth: DevAuthSettings = Field(default_factory=_settings_factory(DevAuthSettings))
    postgres: PostgresSettings = Field(default_factory=_settings_factory(PostgresSettings))
    database: DatabaseSettings = Field(default_factory=_settings_factory(DatabaseSettings))
    redis: RedisSettings = Field(default_factory=_settings_factory(RedisSettings))
    rate_limit: RateLimitSettings = Field(default_factory=_settings_factory(RateLimitSettings))
    minio: MinioSettings = Field(default_factory=_settings_factory(MinioSettings))
    queue: QueueSettings = Field(default_factory=_settings_factory(QueueSettings))
    llm: LlmSettings = Field(default_factory=_settings_factory(LlmSettings))
    deepseek: DeepseekSettings = Field(default_factory=_settings_factory(DeepseekSettings))
    rag: RagSettings = Field(default_factory=_settings_factory(RagSettings))
    embedding: EmbeddingSettings = Field(default_factory=_settings_factory(EmbeddingSettings))
    agents: OpenaiAgentsSettings = Field(default_factory=_settings_factory(OpenaiAgentsSettings))
    n8n: N8nSettings = Field(default_factory=_settings_factory(N8nSettings))
    observability: ObservabilitySettings = Field(
        default_factory=_settings_factory(ObservabilitySettings)
    )
    evaluation: EvaluationSettings = Field(default_factory=_settings_factory(EvaluationSettings))
    frontend: FrontendSettings = Field(default_factory=_settings_factory(FrontendSettings))

    @model_validator(mode="after")
    def _production_guard(self) -> "Settings":
        if self.app.env != "production":
            return self
        offending: list[str] = []
        values = {
            "DATABASE_URL": self.database.url,
            "DEEPSEEK_API_KEY": self.deepseek.api_key,
            "POSTGRES_PASSWORD": self.postgres.password,
            "MINIO_ACCESS_KEY": self.minio.access_key,
            "MINIO_SECRET_KEY": self.minio.secret_key,
            "N8N_API_KEY": self.n8n.api_key,
            "N8N_ENCRYPTION_KEY": self.n8n.encryption_key,
            "GRAFANA_ADMIN_PASSWORD": self.observability.grafana_admin_password,
        }
        # Invariant: the guard must cover exactly the documented required set.
        assert set(values) == set(PRODUCTION_REQUIRED_SECRET_VARS), (
            "production guard drift: guard keys do not match PRODUCTION_REQUIRED_SECRET_VARS"
        )
        for var_name, value in values.items():
            if not value or any(marker in value.lower() for marker in PLACEHOLDER_MARKERS):
                offending.append(var_name)
        problems: list[str] = []
        if offending:
            problems.append("missing or placeholder values for: " + ", ".join(sorted(offending)))
        if self.dev_auth.auth_enabled:
            problems.append("dev auth must be disabled in production (fail closed)")
        if self.llm.provider != "deepseek":
            problems.append("LLM_PROVIDER must be deepseek in production")
        if self.queue.provider != "celery":
            problems.append("QUEUE_PROVIDER must be celery in production")
        if not self.rate_limit.enabled:
            problems.append("RATE_LIMIT_ENABLED must be true in production")
        if self.rate_limit.backend != "redis":
            problems.append("RATE_LIMIT_BACKEND must be redis in production")
        try:
            validate_cors_origins_for_environment(self.app.cors_origins, self.app.env)
        except ValueError:
            problems.append("CORS_ORIGINS must contain production-safe HTTPS origins")
        if problems:
            raise ConfigurationError("; ".join(problems))
        return self


@lru_cache
def get_settings() -> Settings:
    """Cached settings accessor; use ``get_settings.cache_clear()`` in tests."""
    return Settings()


__all__ = [
    "KNOWN_ENV_VARS",
    "PLACEHOLDER_MARKERS",
    "AppSettings",
    "DatabaseSettings",
    "DeepseekSettings",
    "DevAuthSettings",
    "EmbeddingSettings",
    "EvaluationSettings",
    "FrontendSettings",
    "LlmSettings",
    "MinioSettings",
    "N8nSettings",
    "ObservabilitySettings",
    "OpenaiAgentsSettings",
    "PostgresSettings",
    "QueueSettings",
    "RagSettings",
    "RateLimitSettings",
    "RedisSettings",
    "Settings",
    "get_settings",
]
