"""Tests for queue provider wiring and Celery publisher configuration."""

from __future__ import annotations

import uuid

from rag_llm_services_api.core.config import Settings
from rag_llm_services_api.infrastructure.queue import build_task_queue
from rag_llm_services_api.infrastructure.queue.base import (
    EVALUATION_TASK_NAME,
    INGESTION_TASK_NAME,
    EvaluationTaskPayload,
    IngestionTaskPayload,
    MemoryTaskQueue,
)
from rag_llm_services_api.infrastructure.queue.redis_queue import RedisTaskQueue, build_celery_app


def test_build_task_queue_uses_memory_provider_by_default() -> None:
    settings = Settings(_env_file=None)

    queue = build_task_queue(settings)

    assert isinstance(queue, MemoryTaskQueue)


def test_build_celery_app_sets_json_routing_and_visibility_timeout() -> None:
    settings = Settings(_env_file=None)
    settings.queue.ingestion_queue_name = "ingestion_test"
    settings.queue.visibility_timeout_seconds = 120

    app = build_celery_app(settings)

    assert app.conf.task_serializer == "json"
    assert app.conf.result_serializer == "json"
    assert app.conf.accept_content == ["json"]
    assert app.conf.task_acks_late is True
    assert app.conf.task_reject_on_worker_lost is True
    assert app.conf.worker_prefetch_multiplier == 1
    assert app.conf.worker_pool == "threads"
    assert app.conf.worker_concurrency == 4
    assert app.conf.broker_transport_options["visibility_timeout"] == 120
    assert app.conf.task_routes[INGESTION_TASK_NAME]["queue"] == "ingestion_test"
    assert app.conf.task_routes[EVALUATION_TASK_NAME]["queue"] == "ingestion_test"


async def test_redis_task_queue_publishes_stable_task_id() -> None:
    settings = Settings(_env_file=None)
    settings.queue.ingestion_queue_name = "ingestion_test"
    sent: dict[str, object] = {}

    class FakeAsyncResult:
        id = "celery-result-id"

    class FakeCelery:
        def send_task(self, *args: object, **kwargs: object) -> FakeAsyncResult:
            sent["args"] = args
            sent["kwargs"] = kwargs
            return FakeAsyncResult()

    payload = IngestionTaskPayload(
        owner_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
        job_id=uuid.UUID("00000000-0000-0000-0000-000000000010"),
        document_id=uuid.UUID("00000000-0000-0000-0000-000000000020"),
        version_id=uuid.UUID("00000000-0000-0000-0000-000000000030"),
    )
    queue = RedisTaskQueue(settings=settings, celery_app=FakeCelery())  # type: ignore[arg-type]

    result = await queue.enqueue_ingestion_job(payload)

    assert result.task_id == "celery-result-id"
    assert sent["args"] == (INGESTION_TASK_NAME,)
    assert sent["kwargs"] == {
        "kwargs": payload.to_task_kwargs(),
        "task_id": payload.task_id,
        "queue": "ingestion_test",
    }


async def test_memory_task_queue_records_evaluation_payload() -> None:
    queue = MemoryTaskQueue()
    payload = EvaluationTaskPayload(
        owner_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
        run_id=uuid.UUID("00000000-0000-0000-0000-000000000040"),
    )

    result = await queue.enqueue_evaluation_run(payload)

    assert result.task_id == payload.task_id
    assert result.queued is True
    assert queue.evaluation_enqueued == [payload]


async def test_redis_task_queue_publishes_evaluation_task_id() -> None:
    settings = Settings(_env_file=None)
    settings.queue.ingestion_queue_name = "ingestion_test"
    sent: dict[str, object] = {}

    class FakeAsyncResult:
        id = "evaluation-result-id"

    class FakeCelery:
        def send_task(self, *args: object, **kwargs: object) -> FakeAsyncResult:
            sent["args"] = args
            sent["kwargs"] = kwargs
            return FakeAsyncResult()

    payload = EvaluationTaskPayload(
        owner_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
        run_id=uuid.UUID("00000000-0000-0000-0000-000000000040"),
    )
    queue = RedisTaskQueue(settings=settings, celery_app=FakeCelery())  # type: ignore[arg-type]

    result = await queue.enqueue_evaluation_run(payload)

    assert result.task_id == "evaluation-result-id"
    assert sent["args"] == (EVALUATION_TASK_NAME,)
    assert sent["kwargs"] == {
        "kwargs": payload.to_task_kwargs(),
        "task_id": payload.task_id,
        "queue": "ingestion_test",
    }
