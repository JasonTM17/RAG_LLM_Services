"""Typed application settings with fail-fast production validation.

Contract notes:

- Every field maps to exactly one ``.env.example`` key through an explicit
  full-name ``validation_alias``; ``KNOWN_ENV_VARS`` and ``.env.example`` must
  stay in parity (enforced by ``tests/unit/api/test_config.py``).
- ``local``/``development``/``test`` environments get development defaults so
  the app and tests run offline; ``production`` fails fast with safe errors
  when mandatory configuration is missing or still a placeholder, and dev
  auth must be disabled (fail closed, per the operating appendix).
- Error messages name the offending field only and never echo configured
  values, URLs, or placeholder material.
"""

from functools import lru_cache
from typing import Annotated
from uuid import UUID

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from rag_llm_services_shared.errors import ConfigurationError

PLACEHOLDER_MARKERS = ("replace-with", "changeme", "your-", "example")

PRODUCTION_REQUIRED_SECRET_VARS = (
    "DATABASE_URL",
    "DEEPSEEK_API_KEY",
    "POSTGRES_PASSWORD",
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
        "RUN_DEEPSEEK_LIVE_TESTS",
        "LLM_MAX_INPUT_TOKENS",
        "LLM_MAX_OUTPUT_TOKENS",
        "LLM_DAILY_ESTIMATED_COST_LIMIT_USD",
        "LLM_REQUEST_TIMEOUT_SECONDS",
        "RAG_CONTEXT_TOKEN_BUDGET",
        "RAG_RERANK_TOP_K",
        "EMBEDDING_PROVIDER",
        "EMBEDDING_MODEL",
        "RERANKER_PROVIDER",
        "RERANKER_MODEL",
        "OPENAI_TRACING_DISABLED",
        "N8N_BASE_URL",
        "N8N_API_KEY",
        "N8N_ENCRYPTION_KEY",
        "PROMETHEUS_BASE_URL",
        "GRAFANA_BASE_URL",
        "GRAFANA_ADMIN_USER",
        "GRAFANA_ADMIN_PASSWORD",
        "NEXT_PUBLIC_API_BASE_URL",
    }
)


def _alias(name: str) -> dict:
    return {"validation_alias": name}


class AppSettings(BaseSettings):
    """Application identity, logging, and HTTP server surface."""

    model_config = SettingsConfigDict(extra="ignore")

    env: str = Field("local", **_alias("APP_ENV"))
    log_level: str = Field("INFO", **_alias("LOG_LEVEL"))
    api_host: str = Field("0.0.0.0", **_alias("API_HOST"))
    api_port: int = Field(8000, **_alias("API_PORT"))
    # NoDecode: CORS_ORIGINS is a comma-separated string, not JSON; the
    # validator below performs the split.
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:3000"], **_alias("CORS_ORIGINS")
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


class DevAuthSettings(BaseSettings):
    """Local-only principal resolution; production must fail closed."""

    model_config = SettingsConfigDict(extra="ignore")

    auth_enabled: bool = Field(False, **_alias("RAG_DEV_AUTH_ENABLED"))
    user_id: UUID | None = Field(None, **_alias("RAG_DEV_USER_ID"))


class PostgresSettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    db: str = Field("rag_llm_services", **_alias("POSTGRES_DB"))
    user: str = Field("rag_app", **_alias("POSTGRES_USER"))
    password: str = Field("replace-with-local-password", **_alias("POSTGRES_PASSWORD"))


class DatabaseSettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    url: str = Field(
        "postgresql+psycopg://rag_app:replace-with-local-password@postgres:5432/rag_llm_services",
        **_alias("DATABASE_URL"),
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

    url: str = Field("redis://redis:6379/0", **_alias("REDIS_URL"))


class MinioSettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    endpoint: str = Field("http://minio:9000", **_alias("MINIO_ENDPOINT"))
    access_key: str = Field("rag-local", **_alias("MINIO_ACCESS_KEY"))
    secret_key: str = Field("replace-with-local-minio-secret", **_alias("MINIO_SECRET_KEY"))
    bucket: str = Field("rag-documents", **_alias("MINIO_BUCKET"))


class LlmSettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    provider: str = Field("deepseek", **_alias("LLM_PROVIDER"))
    max_input_tokens: int = Field(12000, **_alias("LLM_MAX_INPUT_TOKENS"))
    max_output_tokens: int = Field(2048, **_alias("LLM_MAX_OUTPUT_TOKENS"))
    daily_estimated_cost_limit_usd: float = Field(
        5.0, **_alias("LLM_DAILY_ESTIMATED_COST_LIMIT_USD")
    )
    request_timeout_seconds: int = Field(60, **_alias("LLM_REQUEST_TIMEOUT_SECONDS"))


class DeepseekSettings(BaseSettings):
    """Provider configuration only; the gateway itself arrives in Phase 06."""

    model_config = SettingsConfigDict(extra="ignore")

    api_key: str = Field("replace-with-your-deepseek-api-key", **_alias("DEEPSEEK_API_KEY"))
    base_url: str = Field("https://api.deepseek.com", **_alias("DEEPSEEK_BASE_URL"))
    model: str = Field("deepseek-v4-flash", **_alias("DEEPSEEK_MODEL"))
    api_mode: str = Field("responses", **_alias("DEEPSEEK_API_MODE"))
    allow_chat_completions_fallback: bool = Field(
        False, **_alias("DEEPSEEK_ALLOW_CHAT_COMPLETIONS_FALLBACK")
    )
    run_live_tests: bool = Field(False, **_alias("RUN_DEEPSEEK_LIVE_TESTS"))

    @field_validator("base_url")
    @classmethod
    def _forbid_v1_suffix(cls, value: str) -> str:
        normalized = value.strip().rstrip("/")
        if normalized.endswith("/v1"):
            raise ValueError("DEEPSEEK_BASE_URL must not include the /v1 path suffix")
        return normalized


class RagSettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    context_token_budget: int = Field(6000, **_alias("RAG_CONTEXT_TOKEN_BUDGET"))
    rerank_top_k: int = Field(8, **_alias("RAG_RERANK_TOP_K"))


class EmbeddingSettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    provider: str = Field("bge-m3", **_alias("EMBEDDING_PROVIDER"))
    model: str = Field("BAAI/bge-m3", **_alias("EMBEDDING_MODEL"))
    reranker_provider: str = Field("bge", **_alias("RERANKER_PROVIDER"))
    reranker_model: str = Field("BAAI/bge-reranker-v2-m3", **_alias("RERANKER_MODEL"))


class OpenaiAgentsSettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    tracing_disabled: bool = Field(True, **_alias("OPENAI_TRACING_DISABLED"))


class N8nSettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    base_url: str = Field("http://n8n:5678", **_alias("N8N_BASE_URL"))
    api_key: str = Field("replace-with-local-n8n-api-key", **_alias("N8N_API_KEY"))
    encryption_key: str = Field(
        "replace-with-local-n8n-encryption-key", **_alias("N8N_ENCRYPTION_KEY")
    )


class ObservabilitySettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    prometheus_base_url: str = Field("http://prometheus:9090", **_alias("PROMETHEUS_BASE_URL"))
    grafana_base_url: str = Field("http://grafana:3000", **_alias("GRAFANA_BASE_URL"))
    grafana_admin_user: str = Field("admin", **_alias("GRAFANA_ADMIN_USER"))
    grafana_admin_password: str = Field(
        "replace-with-local-grafana-password", **_alias("GRAFANA_ADMIN_PASSWORD")
    )


class FrontendSettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    next_public_api_base_url: str | None = Field(None, **_alias("NEXT_PUBLIC_API_BASE_URL"))


class Settings(BaseSettings):
    """Root settings object aggregating every configuration domain."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app: AppSettings = Field(default_factory=AppSettings)
    dev_auth: DevAuthSettings = Field(default_factory=DevAuthSettings)
    postgres: PostgresSettings = Field(default_factory=PostgresSettings)
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    minio: MinioSettings = Field(default_factory=MinioSettings)
    llm: LlmSettings = Field(default_factory=LlmSettings)
    deepseek: DeepseekSettings = Field(default_factory=DeepseekSettings)
    rag: RagSettings = Field(default_factory=RagSettings)
    embedding: EmbeddingSettings = Field(default_factory=EmbeddingSettings)
    agents: OpenaiAgentsSettings = Field(default_factory=OpenaiAgentsSettings)
    n8n: N8nSettings = Field(default_factory=N8nSettings)
    observability: ObservabilitySettings = Field(default_factory=ObservabilitySettings)
    frontend: FrontendSettings = Field(default_factory=FrontendSettings)

    @model_validator(mode="after")
    def _production_guard(self) -> "Settings":
        if self.app.env != "production":
            return self
        offending: list[str] = []
        values = {
            "DATABASE_URL": self.database.url,
            "DEEPSEEK_API_KEY": self.deepseek.api_key,
            "POSTGRES_PASSWORD": self.postgres.password,
            "MINIO_SECRET_KEY": self.minio.secret_key,
            "N8N_API_KEY": self.n8n.api_key,
            "N8N_ENCRYPTION_KEY": self.n8n.encryption_key,
            "GRAFANA_ADMIN_PASSWORD": self.observability.grafana_admin_password,
        }
        for var_name, value in values.items():
            if not value or any(marker in value.lower() for marker in PLACEHOLDER_MARKERS):
                offending.append(var_name)
        problems: list[str] = []
        if offending:
            problems.append("missing or placeholder values for: " + ", ".join(sorted(offending)))
        if self.dev_auth.auth_enabled:
            problems.append("dev auth must be disabled in production (fail closed)")
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
    "FrontendSettings",
    "LlmSettings",
    "MinioSettings",
    "N8nSettings",
    "ObservabilitySettings",
    "OpenaiAgentsSettings",
    "PostgresSettings",
    "RagSettings",
    "RedisSettings",
    "Settings",
    "get_settings",
]
