"""Create n8n automation report and evaluation trigger tables.

Revision ID: 0007_n8n_automation_contracts
Revises: 0006_async_worker_job_metadata
Create Date: 2026-09-07
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007_n8n_automation_contracts"
down_revision: str | None = "0006_async_worker_job_metadata"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "automation_reports",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("owner_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("workflow_name", sa.String(length=120), nullable=False),
        sa.Column("run_id", sa.String(length=120), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="RUNNING"),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column(
            "payload_json",
            postgresql.JSONB().with_variant(sa.JSON(), "sqlite"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "owner_id",
            "workflow_name",
            "run_id",
            "status",
            name="uq_automation_reports_idempotency",
        ),
    )
    op.create_index("ix_automation_reports_owner_id", "automation_reports", ["owner_id"])
    op.create_index("ix_automation_reports_workflow_name", "automation_reports", ["workflow_name"])
    op.create_index(
        "ix_automation_reports_owner_created",
        "automation_reports",
        ["owner_id", "created_at"],
    )
    op.create_index(
        "ix_automation_reports_workflow_status",
        "automation_reports",
        ["workflow_name", "status"],
    )

    op.create_table(
        "evaluation_runs",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("owner_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="PENDING"),
        sa.Column("idempotency_key", sa.String(length=120), nullable=True),
        sa.Column("trigger_source", sa.String(length=80), nullable=False, server_default="api"),
        sa.Column("workflow_name", sa.String(length=120), nullable=True),
        sa.Column("dataset_name", sa.String(length=120), nullable=True),
        sa.Column("report_path", sa.String(length=500), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "metadata_json",
            postgresql.JSONB().with_variant(sa.JSON(), "sqlite"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "owner_id",
            "idempotency_key",
            name="uq_evaluation_runs_owner_idempotency_key",
        ),
    )
    op.create_index("ix_evaluation_runs_owner_id", "evaluation_runs", ["owner_id"])
    op.create_index("ix_evaluation_runs_status", "evaluation_runs", ["status"])
    op.create_index(
        "ix_evaluation_runs_owner_created", "evaluation_runs", ["owner_id", "created_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_evaluation_runs_owner_created", table_name="evaluation_runs")
    op.drop_index("ix_evaluation_runs_status", table_name="evaluation_runs")
    op.drop_index("ix_evaluation_runs_owner_id", table_name="evaluation_runs")
    op.drop_table("evaluation_runs")

    op.drop_index("ix_automation_reports_workflow_status", table_name="automation_reports")
    op.drop_index("ix_automation_reports_owner_created", table_name="automation_reports")
    op.drop_index("ix_automation_reports_workflow_name", table_name="automation_reports")
    op.drop_index("ix_automation_reports_owner_id", table_name="automation_reports")
    op.drop_table("automation_reports")
