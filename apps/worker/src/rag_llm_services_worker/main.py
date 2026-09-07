"""Celery worker entrypoint."""

from __future__ import annotations

from rag_llm_services_api.core.config import PLACEHOLDER_MARKERS, Settings, get_settings
from rag_llm_services_api.infrastructure.queue.redis_queue import build_celery_app
from rag_llm_services_observability.logging_setup import configure_logging
from rag_llm_services_observability.metrics import start_metrics_http_server


def _collect_known_secrets(settings: Settings) -> tuple[str, ...]:
    """Configured secret values the worker JSON logger must never emit."""
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


def _configure_observability(settings: Settings) -> None:
    """Configure worker logs and the optional scrape endpoint."""
    configure_logging(
        level=settings.app.log_level.upper(),
        service="rag-llm-services-worker",
        env=settings.app.env,
        known_secrets=_collect_known_secrets(settings),
    )
    if settings.observability.worker_metrics_enabled:
        start_metrics_http_server(
            host=settings.observability.worker_metrics_host,
            port=settings.observability.worker_metrics_port,
        )


settings = get_settings()
_configure_observability(settings)
celery_app = build_celery_app(settings)
celery_app.conf.imports = ("rag_llm_services_worker.tasks",)

__all__ = ["celery_app", "settings"]
