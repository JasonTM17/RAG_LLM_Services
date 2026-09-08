"""Queue provider factory."""

from __future__ import annotations

from rag_llm_services_api.core.config import Settings, get_settings
from rag_llm_services_api.core.errors import ConfigurationError
from rag_llm_services_api.infrastructure.queue.base import (
    EVALUATION_TASK_NAME,
    INGESTION_TASK_NAME,
    EvaluationTaskPayload,
    IngestionTaskPayload,
    MemoryTaskQueue,
    QueueEnqueueResult,
    TaskQueue,
)
from rag_llm_services_api.infrastructure.queue.redis_queue import RedisTaskQueue

_memory_queue = MemoryTaskQueue()


def build_task_queue(settings: Settings) -> TaskQueue:
    """Build the configured queue publisher."""
    if settings.queue.provider == "memory":
        return _memory_queue
    if settings.queue.provider == "celery":
        return RedisTaskQueue(settings=settings)
    raise ConfigurationError("Unsupported queue provider")


def get_task_queue() -> TaskQueue:
    """FastAPI dependency returning the configured queue publisher."""
    return build_task_queue(get_settings())


__all__ = [
    "EVALUATION_TASK_NAME",
    "INGESTION_TASK_NAME",
    "EvaluationTaskPayload",
    "IngestionTaskPayload",
    "MemoryTaskQueue",
    "QueueEnqueueResult",
    "RedisTaskQueue",
    "TaskQueue",
    "build_task_queue",
    "get_task_queue",
]
