"""Ingestion worker task implementation."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from rag_llm_services_api.application.ingestion_pipeline import (
    IngestionPipeline,
    safe_ingestion_error,
)
from rag_llm_services_api.core.config import Settings, get_settings
from rag_llm_services_api.db.session import get_engine
from rag_llm_services_api.domain.documents import DocumentStatus, IngestionJobStatus
from rag_llm_services_api.infrastructure.embeddings import get_embedding_provider
from rag_llm_services_api.infrastructure.queue.base import (
    INGESTION_TASK_NAME,
    IngestionTaskPayload,
)
from rag_llm_services_api.infrastructure.repositories.chunks import ChunkRepository
from rag_llm_services_api.infrastructure.repositories.documents import DocumentRepository
from rag_llm_services_api.infrastructure.storage.base import ObjectStoragePort
from rag_llm_services_api.infrastructure.storage.minio import get_object_storage
from rag_llm_services_embeddings.base import EmbeddingProvider
from rag_llm_services_shared.errors import NotFoundError, ValidationError
from rag_llm_services_worker.main import celery_app
from rag_llm_services_worker.main import settings as celery_settings
from rag_llm_services_worker.metrics import (
    record_error,
    record_worker_ingestion_duration,
    record_worker_ingestion_job,
)

logger = logging.getLogger(__name__)


RETRYING_STATUS = "RETRYING"


class RetryableIngestionError(RuntimeError):
    """Safe error used to ask Celery for another ingestion attempt."""


@dataclass(frozen=True)
class WorkerIngestionResult:
    """JSON-serializable worker task result."""

    owner_id: str
    job_id: str
    document_id: str
    version_id: str
    status: str
    chunk_count: int
    attempt_count: int
    error_message: str | None = None

    def to_dict(self) -> dict[str, str | int | None]:
        """Return a JSON-compatible mapping for Celery result storage."""
        return {
            "owner_id": self.owner_id,
            "job_id": self.job_id,
            "document_id": self.document_id,
            "version_id": self.version_id,
            "status": self.status,
            "chunk_count": self.chunk_count,
            "attempt_count": self.attempt_count,
            "error_message": self.error_message,
        }


def _build_session_maker(settings: Settings) -> async_sessionmaker[AsyncSession]:
    engine = get_engine(settings)
    return async_sessionmaker(engine, expire_on_commit=False)


def _result_from_payload(
    payload: IngestionTaskPayload,
    *,
    status: str,
    chunk_count: int,
    attempt_count: int,
    error_message: str | None = None,
) -> WorkerIngestionResult:
    return WorkerIngestionResult(
        owner_id=str(payload.owner_id),
        job_id=str(payload.job_id),
        document_id=str(payload.document_id),
        version_id=str(payload.version_id),
        status=status,
        chunk_count=chunk_count,
        attempt_count=attempt_count,
        error_message=error_message,
    )


async def _persist_status(
    *,
    session: AsyncSession,
    payload: IngestionTaskPayload,
    document_status: DocumentStatus,
    job_status: IngestionJobStatus,
    error_message: str,
) -> None:
    repo = DocumentRepository(session)
    await repo.update_document_status(
        owner_id=payload.owner_id,
        doc_id=payload.document_id,
        status=document_status.value,
        error_message=error_message,
    )
    await repo.update_ingestion_job_status(
        owner_id=payload.owner_id,
        job_id=payload.job_id,
        status=job_status.value,
        error_message=error_message,
    )
    await session.commit()


async def run_ingestion_task_once(
    payload: IngestionTaskPayload,
    *,
    settings: Settings | None = None,
    session_maker: async_sessionmaker[AsyncSession] | None = None,
    object_storage: ObjectStoragePort | None = None,
    embedding_provider: EmbeddingProvider | None = None,
    final_attempt: bool = True,
    raise_on_failed_result: bool = False,
) -> WorkerIngestionResult:
    """Run one ingestion payload with durable status and metrics updates."""
    cfg = settings or get_settings()
    maker = session_maker or _build_session_maker(cfg)
    started = time.perf_counter()
    attempt_count = 0
    task_result: WorkerIngestionResult | None = None

    async with maker() as session:
        doc_repo = DocumentRepository(session)
        chunk_repo = ChunkRepository(session)
        try:
            job = await doc_repo.get_ingestion_job(payload.owner_id, payload.job_id)
            if job is None:
                raise NotFoundError("Ingestion job not found")
            if (
                job.document_id != payload.document_id
                or job.document_version_id != payload.version_id
            ):
                raise ValidationError("Ingestion task payload does not match durable job")
            if job.status == IngestionJobStatus.INDEXED.value:
                chunk_count = await chunk_repo.count_chunks_by_version(
                    payload.owner_id,
                    payload.version_id,
                )
                task_result = _result_from_payload(
                    payload,
                    status="SKIPPED",
                    chunk_count=chunk_count,
                    attempt_count=job.attempt_count,
                )
            else:
                attempt_job = await doc_repo.record_ingestion_job_attempt(
                    owner_id=payload.owner_id,
                    job_id=payload.job_id,
                    task_id=payload.task_id,
                )
                if attempt_job is None:
                    raise NotFoundError("Ingestion job not found")
                attempt_count = attempt_job.attempt_count
                await session.commit()

                pipeline = IngestionPipeline(
                    object_storage=object_storage or get_object_storage(cfg),
                    document_repo=doc_repo,
                    chunk_repo=chunk_repo,
                    embedding_provider=embedding_provider or get_embedding_provider(cfg),
                )
                result = await pipeline.ingest_document(
                    owner_id=payload.owner_id,
                    document_id=payload.document_id,
                    version_id=payload.version_id,
                    job_id=payload.job_id,
                    persist_failure=final_attempt,
                )
                if result.status == DocumentStatus.FAILED and not final_attempt:
                    await _persist_status(
                        session=session,
                        payload=payload,
                        document_status=DocumentStatus.PROCESSING,
                        job_status=IngestionJobStatus.PROCESSING,
                        error_message=result.error_message or "Ingestion retry pending",
                    )
                else:
                    await session.commit()
                task_result = _result_from_payload(
                    payload,
                    status=RETRYING_STATUS
                    if result.status == DocumentStatus.FAILED and not final_attempt
                    else result.status.value,
                    chunk_count=result.chunk_count,
                    attempt_count=attempt_count,
                    error_message=result.error_message,
                )
        except Exception as exc:  # noqa: BLE001 - persist any worker failure to job state
            await session.rollback()
            error_message = safe_ingestion_error(exc)
            try:
                await _persist_status(
                    session=session,
                    payload=payload,
                    document_status=DocumentStatus.FAILED
                    if final_attempt
                    else DocumentStatus.PROCESSING,
                    job_status=IngestionJobStatus.FAILED
                    if final_attempt
                    else IngestionJobStatus.PROCESSING,
                    error_message=error_message,
                )
            except Exception:
                await session.rollback()
                record_error("worker", "exception")
                logger.exception(
                    "Failed to persist ingestion worker failure state",
                    extra={
                        "stage": "worker.ingestion.persist_failure",
                        "dependency": "database",
                        "status": "failed",
                        "error_code": "WORKER_FAILURE_STATE_FAILED",
                    },
                )
            task_result = _result_from_payload(
                payload,
                status=DocumentStatus.FAILED.value if final_attempt else RETRYING_STATUS,
                chunk_count=0,
                attempt_count=attempt_count,
                error_message=error_message,
            )

    assert task_result is not None
    elapsed_ms = round((time.perf_counter() - started) * 1000.0, 2)
    metric_status = task_result.status.lower()
    if metric_status not in {"indexed", "failed", "skipped", "retrying"}:
        metric_status = "failed"
    record_worker_ingestion_job(metric_status)
    record_worker_ingestion_duration(metric_status, elapsed_ms)
    if metric_status in {"failed", "retrying"}:
        record_error("worker", "exception")
    logger.info(
        "Ingestion worker job completed",
        extra={
            "stage": "worker.ingestion",
            "dependency": "celery",
            "status": metric_status,
            "latency_ms": elapsed_ms,
            "chunk_count": task_result.chunk_count,
            "attempt_count": task_result.attempt_count,
            "error_code": "WORKER_INGESTION_FAILED" if metric_status == "failed" else None,
        },
    )

    if (
        task_result.status in {DocumentStatus.FAILED.value, RETRYING_STATUS}
        and raise_on_failed_result
    ):
        raise RetryableIngestionError(task_result.error_message or "ingestion failed")
    return task_result


@celery_app.task(
    bind=True,
    name=INGESTION_TASK_NAME,
    autoretry_for=(RetryableIngestionError,),
    retry_backoff=celery_settings.queue.ingestion_task_retry_backoff_seconds,
    retry_backoff_max=celery_settings.queue.ingestion_task_retry_backoff_max_seconds,
    retry_jitter=celery_settings.queue.ingestion_task_retry_jitter,
    max_retries=celery_settings.queue.ingestion_task_max_retries,
)
def ingest_document(self: object, **kwargs: str) -> Mapping[str, Any]:
    """Celery task wrapper for ingestion payloads."""
    payload = IngestionTaskPayload.from_task_kwargs(kwargs)
    request = getattr(self, "request", None)
    current_retries = int(getattr(request, "retries", 0) or 0)
    final_attempt = current_retries >= celery_settings.queue.ingestion_task_max_retries
    return asyncio.run(
        run_ingestion_task_once(
            payload,
            final_attempt=final_attempt,
            raise_on_failed_result=not final_attempt,
        )
    ).to_dict()
