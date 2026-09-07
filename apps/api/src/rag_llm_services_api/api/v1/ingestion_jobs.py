"""API router for ingestion jobs."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from rag_llm_services_api.api.dependencies.auth import get_current_user_id
from rag_llm_services_api.api.v1.schemas.documents import IngestionJobResponse, QueueStatusResponse
from rag_llm_services_api.core.config import Settings, get_settings
from rag_llm_services_api.core.errors import NotFoundError, UpstreamUnavailableError
from rag_llm_services_api.db.session import get_session
from rag_llm_services_api.infrastructure.queue import get_task_queue
from rag_llm_services_api.infrastructure.queue.base import TaskQueue
from rag_llm_services_api.infrastructure.repositories.documents import DocumentRepository
from rag_llm_services_observability.metrics import record_worker_queue_depth

router = APIRouter(prefix="/ingestion-jobs", tags=["ingestion-jobs"])


@router.get(
    "/queue",
    response_model=QueueStatusResponse,
    summary="Get ingestion queue status",
)
async def get_ingestion_queue_status(
    owner_id: Annotated[UUID, Depends(get_current_user_id)],
    settings: Annotated[Settings, Depends(get_settings)],
    queue: Annotated[TaskQueue, Depends(get_task_queue)],
) -> QueueStatusResponse:
    """Fetch approximate queue depth for the configured ingestion queue."""
    del owner_id
    try:
        depth = await queue.queue_depth(settings.queue.ingestion_queue_name)
    except Exception as exc:
        raise UpstreamUnavailableError("Ingestion queue status is unavailable") from exc
    record_worker_queue_depth(depth)
    return QueueStatusResponse(queue_name=settings.queue.ingestion_queue_name, depth=depth)


@router.get(
    "/{job_id}",
    response_model=IngestionJobResponse,
    summary="Get ingestion job status",
)
async def get_ingestion_job(
    job_id: UUID,
    owner_id: Annotated[UUID, Depends(get_current_user_id)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> IngestionJobResponse:
    """Fetch status and details of an ingestion job scoped to the owner."""
    repo = DocumentRepository(session)
    job = await repo.get_ingestion_job(owner_id, job_id)
    if job is None:
        raise NotFoundError("Ingestion job not found")
    return IngestionJobResponse.model_validate(job)
