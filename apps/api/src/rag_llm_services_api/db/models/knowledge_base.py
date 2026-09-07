"""SQLAlchemy model for knowledge bases."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Index, String, Text, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from rag_llm_services_api.db.base import Base

if TYPE_CHECKING:
    from rag_llm_services_api.db.models.document import DocumentModel


class KnowledgeBaseModel(Base):
    """Knowledge base database entity."""

    __tablename__ = "knowledge_bases"
    __table_args__ = (
        UniqueConstraint("owner_id", "name", name="uq_knowledge_bases_owner_name"),
        Index("ix_knowledge_bases_owner_created", "owner_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    documents: Mapped[list[DocumentModel]] = relationship(
        "DocumentModel",
        back_populates="knowledge_base",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
