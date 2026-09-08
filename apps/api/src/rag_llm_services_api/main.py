"""FastAPI application assembly for RAG LLM Services.

Routers delegate to application services; they never call SQL directly.
Business logic must not import FastAPI request objects. External clients
(postgres, redis, minio, providers) are reached only through infrastructure
adapters behind package boundaries.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from rag_llm_services_api.api.health import router as health_router
from rag_llm_services_api.api.metrics import router as metrics_router
from rag_llm_services_api.api.v1.router import router as api_v1_router
from rag_llm_services_api.core.config import PLACEHOLDER_MARKERS, Settings, get_settings
from rag_llm_services_api.core.error_handlers import register_exception_handlers
from rag_llm_services_api.core.middleware import (
    MetricsMiddleware,
    RequestIdMiddleware,
    SecurityHeadersMiddleware,
)
from rag_llm_services_api.core.rate_limit import RateLimitMiddleware, build_rate_limit_store
from rag_llm_services_api.db.session import dispose_engine
from rag_llm_services_api.infrastructure.llm import dispose_llm_provider
from rag_llm_services_observability.logging_setup import configure_logging


def _collect_known_secrets(settings: Settings) -> tuple[str, ...]:
    """Configured secret values the JSON log formatter must never emit.

    Placeholder values are skipped: they are not real credentials and
    redacting them would make log triage harder for no security gain.
    Short (< 6 chars) or empty values are also skipped to prevent over-redaction.
    """
    candidates = (
        settings.postgres.password,
        settings.minio.access_key,
        settings.minio.secret_key,
        settings.deepseek.api_key,
        settings.n8n.api_key,
        settings.n8n.encryption_key,
        settings.observability.grafana_admin_password,
    )
    return tuple(
        value
        for value in candidates
        if value
        and len(value) >= 6
        and not any(marker in value.lower() for marker in PLACEHOLDER_MARKERS)
    )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(
        level=settings.app.log_level.upper(),
        service="rag-llm-services-api",
        env=settings.app.env,
        known_secrets=_collect_known_secrets(settings),
    )
    yield
    await dispose_llm_provider()
    await dispose_engine()


def create_app() -> FastAPI:
    app = FastAPI(
        title="RAG LLM Services API",
        version="0.1.0",
        lifespan=lifespan,
    )
    register_exception_handlers(app)

    settings = get_settings()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.app.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(
        RateLimitMiddleware,
        enabled=settings.rate_limit.enabled,
        requests_per_window=settings.rate_limit.requests_per_window,
        window_seconds=settings.rate_limit.window_seconds,
        store=build_rate_limit_store(
            settings.rate_limit.backend,
            redis_url=settings.redis.url,
        ),
        fail_closed=settings.app.env == "production",
    )
    app.add_middleware(MetricsMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)
    # Added last so it is outermost: request IDs cover CORS preflight too.
    app.add_middleware(RequestIdMiddleware)

    app.include_router(health_router)
    app.include_router(metrics_router)
    app.include_router(api_v1_router, prefix="/api/v1")
    return app


app = create_app()
