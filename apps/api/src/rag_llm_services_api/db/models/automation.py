"""SQLAlchemy models for n8n orchestration contracts."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Index, String, Text, UniqueConstraint, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from rag_llm_services_api.db.base import Base
from rag_llm_services_api.domain.automation import AutomationRunStatus, EvaluationRunStatus


class AutomationReportModel(Base):
    """Audit row written by n8n workflows after bounded orchestration steps."""

    __tablename__ = "automation_reports"
    __table_args__ = (
        UniqueConstraint(
            "owner_id",
            "workflow_name",
            "run_id",
            "status",
            name="uq_automation_reports_idempotency",
        ),
        Index("ix_automation_reports_owner_created", "owner_id", "created_at"),
        Index("ix_automation_reports_workflow_status", "workflow_name", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    workflow_name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    run_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default=AutomationRunStatus.RUNNING.value
    )
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"), nullable=False, default=dict
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class EvaluationRunModel(Base):
    """Minimal evaluation trigger/status row used by n8n until Phase 12 expands it."""

    __tablename__ = "evaluation_runs"
    __table_args__ = (
        UniqueConstraint(
            "owner_id",
            "idempotency_key",
            name="uq_evaluation_runs_owner_idempotency_key",
        ),
        Index("ix_evaluation_runs_owner_created", "owner_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default=EvaluationRunStatus.PENDING.value, index=True
    )
    idempotency_key: Mapped[str | None] = mapped_column(String(120), nullable=True)
    trigger_source: Mapped[str] = mapped_column(String(80), nullable=False, default="api")
    workflow_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    dataset_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    report_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"), nullable=False, default=dict
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
