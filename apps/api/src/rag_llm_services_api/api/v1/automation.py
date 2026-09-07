"""API router for source-controlled n8n workflow audit reports."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from rag_llm_services_api.api.dependencies.auth import get_current_user_id
from rag_llm_services_api.api.v1.schemas.automation import (
    AutomationReportRequest,
    AutomationReportResponse,
)
from rag_llm_services_api.db.models.automation import AutomationReportModel
from rag_llm_services_api.db.session import get_session
from rag_llm_services_api.infrastructure.repositories.automation import (
    AutomationReportCreate,
    AutomationRepository,
)

router = APIRouter(prefix="/automation", tags=["automation"])


@router.post(
    "/reports",
    response_model=AutomationReportResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Record an n8n workflow report",
)
async def create_automation_report(
    payload: AutomationReportRequest,
    owner_id: Annotated[UUID, Depends(get_current_user_id)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AutomationReportResponse:
    """Persist one owner-scoped workflow report row."""
    repo = AutomationRepository(session)
    report: AutomationReportModel
    try:
        report = await repo.create_report(
            AutomationReportCreate(
                owner_id=owner_id,
                workflow_name=payload.workflow_name,
                run_id=payload.run_id,
                status=payload.status,
                summary=payload.summary,
                payload_json=payload.payload,
            )
        )
        await session.commit()
    except IntegrityError:
        await session.rollback()
        existing_report = await repo.get_report_by_idempotency_key(
            owner_id=owner_id,
            workflow_name=payload.workflow_name,
            run_id=payload.run_id,
            status=payload.status,
        )
        if existing_report is None:
            raise
        report = existing_report
    except Exception:
        await session.rollback()
        raise
    return AutomationReportResponse.model_validate(report)
