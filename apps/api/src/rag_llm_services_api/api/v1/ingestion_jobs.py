"""API router for ingestion jobs."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from rag_llm_services_api.api.dependencies.auth import get_current_user_id
from rag_llm_services_api.api.v1.schemas.documents import IngestionJobResponse
from rag_llm_services_api.core.errors import NotFoundError
from rag_llm_services_api.db.session import get_session
from rag_llm_services_api.infrastructure.repositories.documents import DocumentRepository

router = APIRouter(prefix="/ingestion-jobs", tags=["ingestion-jobs"])


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
