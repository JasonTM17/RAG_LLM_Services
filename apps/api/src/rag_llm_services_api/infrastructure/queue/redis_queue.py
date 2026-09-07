"""Celery/Redis queue publisher for ingestion jobs."""

from __future__ import annotations

import redis.asyncio
from celery import Celery

from rag_llm_services_api.core.config import Settings
from rag_llm_services_api.infrastructure.queue.base import (
    INGESTION_TASK_NAME,
    IngestionTaskPayload,
    QueueEnqueueResult,
)


def build_celery_app(settings: Settings) -> Celery:
    """Build a Celery app configured for Redis broker/result backend."""
    app = Celery(
        "rag_llm_services",
        broker=settings.queue.celery_broker_url,
        backend=settings.queue.celery_result_backend,
    )
    visibility_timeout = settings.queue.visibility_timeout_seconds
    app.conf.update(
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
        timezone="UTC",
        enable_utc=True,
        task_acks_late=True,
        task_reject_on_worker_lost=True,
        worker_prefetch_multiplier=1,
        worker_pool=settings.queue.worker_pool,
        worker_concurrency=settings.queue.worker_concurrency,
        broker_transport_options={"visibility_timeout": visibility_timeout},
        result_backend_transport_options={"visibility_timeout": visibility_timeout},
        task_routes={INGESTION_TASK_NAME: {"queue": settings.queue.ingestion_queue_name}},
    )
    return app


class RedisTaskQueue:
    """Task publisher backed by Celery over Redis."""

    def __init__(self, *, settings: Settings, celery_app: Celery | None = None) -> None:
        self._settings = settings
        self._celery = celery_app or build_celery_app(settings)

    async def enqueue_ingestion_job(self, payload: IngestionTaskPayload) -> QueueEnqueueResult:
        result = self._celery.send_task(
            INGESTION_TASK_NAME,
            kwargs=payload.to_task_kwargs(),
            task_id=payload.task_id,
            queue=self._settings.queue.ingestion_queue_name,
        )
        return QueueEnqueueResult(task_id=str(result.id), queued=True)

    async def queue_depth(self, queue_name: str) -> int:
        async with redis.asyncio.from_url(self._settings.queue.celery_broker_url) as client:
            return int(await client.llen(queue_name))
