"""SQLAlchemy model for recording retrieval query events and evaluation audit logs."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Float, Index, Integer, String, Text, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from rag_llm_services_api.db.base import Base


class RagQueryModel(Base):
    """Audit and evaluation record of an executed retrieval query."""

    __tablename__ = "rag_queries"
    __table_args__ = (Index("ix_rag_queries_owner_created", "owner_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    query_text: Mapped[str] = mapped_column(Text, nullable=False)
    knowledge_base_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    retrieval_method: Mapped[str] = mapped_column(String(50), nullable=False)
    vector_top_k: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    keyword_top_k: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    rerank_top_k: Mapped[int] = mapped_column(Integer, nullable=False, default=8)
    result_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    latency_ms: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    filter_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"), nullable=False, default=dict
    )
    stage_latencies_ms: Mapped[dict[str, float]] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"), nullable=False, default=dict
    )
    result_chunk_ids: Mapped[list[str]] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"), nullable=False, default=list
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
