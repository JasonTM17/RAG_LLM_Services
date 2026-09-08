"""Create locally owned chat conversations, messages, and LLM usage audit rows.

Revision ID: 0005_chat_and_llm_usage
Revises: 0004_hybrid_retrieval
Create Date: 2026-09-07

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0005_chat_and_llm_usage"
down_revision: str | None = "0004_hybrid_retrieval"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create conversation, message, and LLM usage tables."""
    op.create_table(
        "conversations",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("owner_id", sa.Uuid(as_uuid=True), nullable=False, index=True),
        sa.Column("title", sa.String(length=255), nullable=False),
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
    )
    op.create_index("ix_conversations_owner_updated", "conversations", ["owner_id", "updated_at"])
    op.create_index("ix_conversations_owner_created", "conversations", ["owner_id", "created_at"])

    op.create_table(
        "messages",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("owner_id", sa.Uuid(as_uuid=True), nullable=False, index=True),
        sa.Column(
            "conversation_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("conversations.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("role", sa.String(length=30), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
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
    )
    op.create_index(
        "ix_messages_owner_conversation_created",
        "messages",
        ["owner_id", "conversation_id", "created_at"],
    )

    op.create_table(
        "llm_usage",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("owner_id", sa.Uuid(as_uuid=True), nullable=False, index=True),
        sa.Column(
            "conversation_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("conversations.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "message_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("messages.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("model", sa.String(length=120), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cached_input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("estimated_cost_usd", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("latency_ms", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_llm_usage_owner_created", "llm_usage", ["owner_id", "created_at"])


def downgrade() -> None:
    """Drop LLM usage, messages, and conversations."""
    op.drop_index("ix_llm_usage_owner_created", table_name="llm_usage")
    op.drop_table("llm_usage")
    op.drop_index("ix_messages_owner_conversation_created", table_name="messages")
    op.drop_table("messages")
    op.drop_index("ix_conversations_owner_created", table_name="conversations")
    op.drop_index("ix_conversations_owner_updated", table_name="conversations")
    op.drop_table("conversations")
