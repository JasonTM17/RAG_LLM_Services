"""Queue abstractions for async ingestion and evaluation jobs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

INGESTION_TASK_NAME = "rag_llm_services_worker.ingest_document"
EVALUATION_TASK_NAME = "rag_llm_services_worker.run_evaluation"


@dataclass(frozen=True)
class IngestionTaskPayload:
    """Server-created ingestion task payload."""

    owner_id: UUID
    job_id: UUID
    document_id: UUID
    version_id: UUID

    @property
    def task_id(self) -> str:
        return f"ingestion:{self.job_id}:{self.version_id}"

    def to_task_kwargs(self) -> dict[str, str]:
        """Serialize payload for Celery or JSON-compatible queues."""
        return {
            "owner_id": str(self.owner_id),
            "job_id": str(self.job_id),
            "document_id": str(self.document_id),
            "version_id": str(self.version_id),
        }

    @classmethod
    def from_task_kwargs(cls, payload: dict[str, str]) -> IngestionTaskPayload:
        """Parse payload received by a worker task."""
        return cls(
            owner_id=UUID(payload["owner_id"]),
            job_id=UUID(payload["job_id"]),
            document_id=UUID(payload["document_id"]),
            version_id=UUID(payload["version_id"]),
        )


@dataclass(frozen=True)
class EvaluationTaskPayload:
    """Server-created evaluation task payload."""

    owner_id: UUID
    run_id: UUID

    @property
    def task_id(self) -> str:
        return f"evaluation:{self.run_id}"

    def to_task_kwargs(self) -> dict[str, str]:
        """Serialize payload for Celery or JSON-compatible queues."""
        return {
            "owner_id": str(self.owner_id),
            "run_id": str(self.run_id),
        }

    @classmethod
    def from_task_kwargs(cls, payload: dict[str, str]) -> EvaluationTaskPayload:
        """Parse payload received by a worker task."""
        return cls(
            owner_id=UUID(payload["owner_id"]),
            run_id=UUID(payload["run_id"]),
        )


@dataclass(frozen=True)
class QueueEnqueueResult:
    """Result returned after publishing a task."""

    task_id: str
    queued: bool


class TaskQueue(Protocol):
    """Async queue publisher consumed by API routes."""

    async def enqueue_ingestion_job(self, payload: IngestionTaskPayload) -> QueueEnqueueResult:
        """Publish one ingestion task."""
        ...

    async def enqueue_evaluation_run(self, payload: EvaluationTaskPayload) -> QueueEnqueueResult:
        """Publish one evaluation task."""
        ...

    async def queue_depth(self, queue_name: str) -> int:
        """Return an approximate queue depth when supported."""
        ...


class MemoryTaskQueue:
    """In-process queue used by local tests and offline development."""

    def __init__(self) -> None:
        self.enqueued: list[IngestionTaskPayload] = []
        self.evaluation_enqueued: list[EvaluationTaskPayload] = []

    async def enqueue_ingestion_job(self, payload: IngestionTaskPayload) -> QueueEnqueueResult:
        self.enqueued.append(payload)
        return QueueEnqueueResult(task_id=payload.task_id, queued=True)

    async def enqueue_evaluation_run(self, payload: EvaluationTaskPayload) -> QueueEnqueueResult:
        self.evaluation_enqueued.append(payload)
        return QueueEnqueueResult(task_id=payload.task_id, queued=True)

    async def queue_depth(self, queue_name: str) -> int:
        del queue_name
        return len(self.enqueued) + len(self.evaluation_enqueued)
