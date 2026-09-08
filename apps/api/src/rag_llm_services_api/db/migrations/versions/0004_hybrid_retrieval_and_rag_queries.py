"""Add full-text search GIN index on document_chunks and create rag_queries table.

Revision ID: 0004_hybrid_retrieval
Revises: 0003_document_chunks_pgvector
Create Date: 2026-09-07

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0004_hybrid_retrieval"
down_revision: str | None = "0003_document_chunks_pgvector"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create GIN full-text search index and rag_queries audit table."""
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    # 1. Add GIN index for PostgreSQL full-text search
    if is_postgres:
        op.execute(
            "CREATE INDEX IF NOT EXISTS ix_document_chunks_content_tsv "
            "ON document_chunks USING gin (to_tsvector('english', content));"
        )

    # 2. Create rag_queries evaluation and audit table
    op.create_table(
        "rag_queries",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("owner_id", sa.Uuid(as_uuid=True), nullable=False, index=True),
        sa.Column("query_text", sa.Text(), nullable=False),
        sa.Column("knowledge_base_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("retrieval_method", sa.String(length=50), nullable=False),
        sa.Column("vector_top_k", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("keyword_top_k", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("rerank_top_k", sa.Integer(), nullable=False, server_default="8"),
        sa.Column("result_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("latency_ms", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column(
            "filter_json",
            postgresql.JSONB().with_variant(sa.JSON(), "sqlite"),
            nullable=False,
        ),
        sa.Column(
            "stage_latencies_ms",
            postgresql.JSONB().with_variant(sa.JSON(), "sqlite"),
            nullable=False,
        ),
        sa.Column(
            "result_chunk_ids",
            postgresql.JSONB().with_variant(sa.JSON(), "sqlite"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_index(
        "ix_rag_queries_owner_created",
        "rag_queries",
        ["owner_id", "created_at"],
    )


def downgrade() -> None:
    """Drop rag_queries table and GIN index."""
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    op.drop_index("ix_rag_queries_owner_created", table_name="rag_queries")
    op.drop_table("rag_queries")

    if is_postgres:
        op.execute("DROP INDEX IF EXISTS ix_document_chunks_content_tsv;")
