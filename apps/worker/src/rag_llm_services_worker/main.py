"""Celery worker entrypoint."""

from __future__ import annotations

from rag_llm_services_api.core.config import get_settings
from rag_llm_services_api.infrastructure.queue.redis_queue import build_celery_app

settings = get_settings()
celery_app = build_celery_app(settings)
celery_app.conf.imports = ("rag_llm_services_worker.tasks",)

__all__ = ["celery_app"]
