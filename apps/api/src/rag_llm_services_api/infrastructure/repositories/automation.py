"""Repository for n8n automation and evaluation orchestration rows."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, cast
from uuid import UUID

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from rag_llm_services_api.db.models.automation import AutomationReportModel, EvaluationRunModel
from rag_llm_services_api.domain.automation import EvaluationRunStatus


@dataclass(frozen=True)
class AutomationReportCreate:
    """Input for creating an automation report row."""

    owner_id: UUID
    workflow_name: str
    status: str
    run_id: str | None = None
    summary: str | None = None
    payload_json: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EvaluationRunCreate:
    """Input for creating a minimal evaluation run row."""

    owner_id: UUID
    trigger_source: str
    idempotency_key: str | None = None
    workflow_name: str | None = None
    dataset_name: str | None = None
    metadata_json: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EvaluationRunUpdate:
    """Mutable evaluation fields written after a run attempt."""

    status: str
    dataset_name: str | None = None
    report_path: str | None = None
    error_message: str | None = None
    metadata_json: dict[str, Any] = field(default_factory=dict)


class AutomationRepository:
    """Async repository for workflow report and evaluation trigger records."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_report(self, data: AutomationReportCreate) -> AutomationReportModel:
        """Persist one owner-scoped automation report row."""
        existing = await self.get_report_by_idempotency_key(
            owner_id=data.owner_id,
            workflow_name=data.workflow_name,
            run_id=data.run_id,
            status=data.status,
        )
        if existing is not None:
            return existing

        report = AutomationReportModel(
            owner_id=data.owner_id,
            workflow_name=data.workflow_name,
            run_id=data.run_id,
            status=data.status,
            summary=data.summary,
            payload_json=dict(data.payload_json),
        )
        self._session.add(report)
        await self._session.flush()
        await self._session.refresh(report)
        return report

    async def get_report_by_idempotency_key(
        self,
        *,
        owner_id: UUID,
        workflow_name: str,
        run_id: str | None,
        status: str,
    ) -> AutomationReportModel | None:
        """Fetch an existing report for a retry of the same workflow execution."""
        if run_id is None:
            return None
        stmt = select(AutomationReportModel).where(
            AutomationReportModel.owner_id == owner_id,
            AutomationReportModel.workflow_name == workflow_name,
            AutomationReportModel.run_id == run_id,
            AutomationReportModel.status == status,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def create_evaluation_run(
        self,
        data: EvaluationRunCreate,
    ) -> tuple[EvaluationRunModel, bool]:
        """Persist an evaluation trigger row or return an idempotent existing row."""
        existing = await self.get_evaluation_run_by_idempotency_key(
            owner_id=data.owner_id,
            idempotency_key=data.idempotency_key,
        )
        if existing is not None:
            return existing, False

        run = EvaluationRunModel(
            owner_id=data.owner_id,
            status=EvaluationRunStatus.PENDING.value,
            idempotency_key=data.idempotency_key,
            trigger_source=data.trigger_source,
            workflow_name=data.workflow_name,
            dataset_name=data.dataset_name,
            metadata_json=dict(data.metadata_json),
        )
        self._session.add(run)
        await self._session.flush()
        await self._session.refresh(run)
        return run, True

    async def update_evaluation_run(
        self,
        run: EvaluationRunModel,
        data: EvaluationRunUpdate,
    ) -> EvaluationRunModel:
        """Persist evaluation execution status and safe result metadata."""
        run.status = data.status
        if data.dataset_name is not None:
            run.dataset_name = data.dataset_name
        run.report_path = data.report_path
        run.error_message = data.error_message
        run.metadata_json = dict(data.metadata_json)
        await self._session.flush()
        await self._session.refresh(run)
        return run

    async def claim_evaluation_run(
        self,
        *,
        owner_id: UUID,
        run_id: UUID,
        stale_before: datetime | None = None,
    ) -> tuple[EvaluationRunModel | None, bool]:
        """Atomically move a pending or stale running evaluation run to RUNNING."""
        claimable_status = EvaluationRunModel.status == EvaluationRunStatus.PENDING.value
        if stale_before is not None:
            claimable_status = or_(
                claimable_status,
                and_(
                    EvaluationRunModel.status == EvaluationRunStatus.RUNNING.value,
                    EvaluationRunModel.updated_at < stale_before,
                ),
            )
        stmt = (
            update(EvaluationRunModel)
            .where(
                EvaluationRunModel.owner_id == owner_id,
                EvaluationRunModel.id == run_id,
                claimable_status,
            )
            .values(
                status=EvaluationRunStatus.RUNNING.value,
                error_message=None,
                updated_at=func.now(),
            )
        )
        result = cast(CursorResult[Any], await self._session.execute(stmt))
        run = await self.get_evaluation_run(owner_id=owner_id, run_id=run_id)
        return run, bool(result.rowcount)

    async def get_evaluation_run(
        self,
        owner_id: UUID,
        run_id: UUID,
    ) -> EvaluationRunModel | None:
        """Fetch one evaluation run scoped to owner."""
        stmt = select(EvaluationRunModel).where(
            EvaluationRunModel.owner_id == owner_id,
            EvaluationRunModel.id == run_id,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_evaluation_run_by_idempotency_key(
        self,
        *,
        owner_id: UUID,
        idempotency_key: str | None,
    ) -> EvaluationRunModel | None:
        """Fetch an existing evaluation trigger for a retry of the same external run."""
        if idempotency_key is None:
            return None
        stmt = select(EvaluationRunModel).where(
            EvaluationRunModel.owner_id == owner_id,
            EvaluationRunModel.idempotency_key == idempotency_key,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()
