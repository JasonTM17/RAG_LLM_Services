"""API router for evaluation trigger/status contracts."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from rag_llm_services_api.api.dependencies.auth import get_current_user_id
from rag_llm_services_api.api.v1.schemas.automation import (
    EvaluationCreateRequest,
    EvaluationRunResponse,
)
from rag_llm_services_api.core.errors import NotFoundError
from rag_llm_services_api.db.models.automation import EvaluationRunModel
from rag_llm_services_api.db.session import get_session
from rag_llm_services_api.infrastructure.repositories.automation import (
    AutomationRepository,
    EvaluationRunCreate,
)

router = APIRouter(prefix="/evaluations", tags=["evaluations"])


@router.post(
    "",
    response_model=EvaluationRunResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger a RAG evaluation run",
)
async def create_evaluation_run(
    payload: EvaluationCreateRequest,
    owner_id: Annotated[UUID, Depends(get_current_user_id)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> EvaluationRunResponse:
    """Record a queued evaluation trigger; Phase 12 implements execution."""
    repo = AutomationRepository(session)
    run: EvaluationRunModel
    try:
        run = await repo.create_evaluation_run(
            EvaluationRunCreate(
                owner_id=owner_id,
                trigger_source=payload.trigger_source,
                idempotency_key=payload.idempotency_key,
                workflow_name=payload.workflow_name,
                dataset_name=payload.dataset_name,
                metadata_json=payload.metadata,
            )
        )
        await session.commit()
    except IntegrityError:
        await session.rollback()
        existing_run = await repo.get_evaluation_run_by_idempotency_key(
            owner_id=owner_id,
            idempotency_key=payload.idempotency_key,
        )
        if existing_run is None:
            raise
        run = existing_run
    except Exception:
        await session.rollback()
        raise
    return EvaluationRunResponse.model_validate(run)


@router.get(
    "/{run_id}",
    response_model=EvaluationRunResponse,
    summary="Get evaluation run status",
)
async def get_evaluation_run(
    run_id: UUID,
    owner_id: Annotated[UUID, Depends(get_current_user_id)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> EvaluationRunResponse:
    """Fetch a minimal evaluation run status scoped to the owner."""
    repo = AutomationRepository(session)
    run = await repo.get_evaluation_run(owner_id=owner_id, run_id=run_id)
    if run is None:
        raise NotFoundError("Evaluation run not found")
    return EvaluationRunResponse.model_validate(run)
