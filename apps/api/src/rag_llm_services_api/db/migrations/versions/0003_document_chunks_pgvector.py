"""Add pgvector extension and 1024-dim embedding column to document_chunks.

Revision ID: 0003_document_chunks_pgvector
Revises: 0002_document_management
Create Date: 2026-09-07

"""

from collections.abc import Sequence

import pgvector.sqlalchemy
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003_document_chunks_pgvector"
down_revision: str | None = "0002_document_management"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Enable pgvector extension and add 1024-dim embedding column with HNSW index."""
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    # 1. Ensure pgvector extension exists on PostgreSQL
    if is_postgres:
        op.execute("CREATE EXTENSION IF NOT EXISTS vector;")

    # 2. Add embedding column (1024 dimensions for BGE-M3 dense embeddings)
    op.add_column(
        "document_chunks",
        sa.Column("embedding", pgvector.sqlalchemy.Vector(1024), nullable=True),
    )

    # 3. Create HNSW index for cosine distance on PostgreSQL
    # HNSW provides high recall and fast approximate nearest neighbors
    if is_postgres:
        op.execute(
            "CREATE INDEX IF NOT EXISTS ix_document_chunks_embedding_hnsw "
            "ON document_chunks USING hnsw (embedding vector_cosine_ops);"
        )


def downgrade() -> None:
    """Drop HNSW index and embedding column."""
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    if is_postgres:
        op.execute("DROP INDEX IF EXISTS ix_document_chunks_embedding_hnsw;")

    op.drop_column("document_chunks", "embedding")
