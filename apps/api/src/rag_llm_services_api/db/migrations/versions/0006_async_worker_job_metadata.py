"""Add ingestion job queue metadata.

Revision ID: 0006_async_worker_job_metadata
Revises: 0005_chat_and_llm_usage
Create Date: 2026-09-07
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_async_worker_job_metadata"
down_revision: str | None = "0005_chat_and_llm_usage"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "ingestion_jobs",
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column("ingestion_jobs", sa.Column("queued_task_id", sa.String(length=255)))
    op.create_index("ix_ingestion_jobs_queued_task_id", "ingestion_jobs", ["queued_task_id"])


def downgrade() -> None:
    op.drop_index("ix_ingestion_jobs_queued_task_id", table_name="ingestion_jobs")
    op.drop_column("ingestion_jobs", "queued_task_id")
    op.drop_column("ingestion_jobs", "attempt_count")
