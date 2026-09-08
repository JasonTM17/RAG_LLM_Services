"""API router for evaluation trigger/status contracts."""

from __future__ import annotations

import asyncio
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
from rag_llm_services_api.application.evaluation_service import EvaluationApplicationService
from rag_llm_services_api.core.config import Settings, get_settings
from rag_llm_services_api.core.errors import NotFoundError
from rag_llm_services_api.db.models.automation import EvaluationRunModel
from rag_llm_services_api.db.session import get_session
from rag_llm_services_api.domain.automation import EvaluationRunStatus
from rag_llm_services_api.infrastructure.queue import get_task_queue
from rag_llm_services_api.infrastructure.queue.base import EvaluationTaskPayload, TaskQueue
from rag_llm_services_api.infrastructure.repositories.automation import AutomationRepository
from rag_llm_services_shared.errors import UpstreamUnavailableError

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
    settings: Annotated[Settings, Depends(get_settings)],
    queue: Annotated[TaskQueue, Depends(get_task_queue)],
) -> EvaluationRunResponse:
    """Create a queued fixture-safe RAG evaluation run for the worker lane."""
    repo = AutomationRepository(session)
    service = EvaluationApplicationService(repo, settings)
    should_enqueue = False
    try:
        outcome = await service.create_queued(
            owner_id=owner_id,
            trigger_source=payload.trigger_source,
            idempotency_key=payload.idempotency_key,
            workflow_name=payload.workflow_name,
            dataset_name=payload.dataset_name,
            metadata=payload.metadata,
        )
        run = outcome.run
        should_enqueue = outcome.created or run.status == EvaluationRunStatus.PENDING.value
        await session.commit()
    except IntegrityError:
        await session.rollback()
        existing_run = await _existing_run_after_integrity_error(
            repo=repo,
            owner_id=owner_id,
            idempotency_key=payload.idempotency_key,
        )
        if existing_run is None:
            raise
        run = existing_run
        should_enqueue = run.status == EvaluationRunStatus.PENDING.value
    except Exception:
        await session.rollback()
        raise

    if should_enqueue:
        await _enqueue_evaluation_or_fail(
            session=session,
            service=service,
            owner_id=owner_id,
            run_id=run.id,
            queue=queue,
        )
    return _response_from_run(run)


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
    return _response_from_run(run)


def _response_from_run(run: EvaluationRunModel) -> EvaluationRunResponse:
    response = EvaluationRunResponse.model_validate(run)
    result = run.metadata_json.get("result")
    if not isinstance(result, dict):
        return response
    return response.model_copy(update={"result": result})


async def _existing_run_after_integrity_error(
    *,
    repo: AutomationRepository,
    owner_id: UUID,
    idempotency_key: str | None,
) -> EvaluationRunModel | None:
    for delay_seconds in (0.0, 0.01, 0.05):
        if delay_seconds:
            await asyncio.sleep(delay_seconds)
        existing = await repo.get_evaluation_run_by_idempotency_key(
            owner_id=owner_id,
            idempotency_key=idempotency_key,
        )
        if existing is not None:
            return existing
    return None


async def _enqueue_evaluation_or_fail(
    *,
    session: AsyncSession,
    service: EvaluationApplicationService,
    owner_id: UUID,
    run_id: UUID,
    queue: TaskQueue,
) -> None:
    try:
        await queue.enqueue_evaluation_run(EvaluationTaskPayload(owner_id=owner_id, run_id=run_id))
    except Exception as exc:
        await session.rollback()
        await service.mark_queue_failure(owner_id=owner_id, run_id=run_id)
        await session.commit()
        raise UpstreamUnavailableError("Evaluation queue is unavailable") from exc
