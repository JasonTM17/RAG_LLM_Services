"""SQLAlchemy models for documents and document versions."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from rag_llm_services_api.db.base import Base
from rag_llm_services_api.domain.documents import DocumentStatus

if TYPE_CHECKING:
    from rag_llm_services_api.db.models.chunk import DocumentChunkModel
    from rag_llm_services_api.db.models.ingestion_job import IngestionJobModel
    from rag_llm_services_api.db.models.knowledge_base import KnowledgeBaseModel


class DocumentModel(Base):
    """Document database entity."""

    __tablename__ = "documents"
    __table_args__ = (
        Index("ix_documents_owner_kb", "owner_id", "knowledge_base_id"),
        Index("ix_documents_owner_created", "owner_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    knowledge_base_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("knowledge_bases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default=DocumentStatus.UPLOADED.value, index=True
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    current_version_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    knowledge_base: Mapped[KnowledgeBaseModel] = relationship(
        "KnowledgeBaseModel", back_populates="documents"
    )
    versions: Mapped[list[DocumentVersionModel]] = relationship(
        "DocumentVersionModel",
        back_populates="document",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="DocumentVersionModel.version_number",
    )
    ingestion_jobs: Mapped[list[IngestionJobModel]] = relationship(
        "IngestionJobModel",
        back_populates="document",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    chunks: Mapped[list[DocumentChunkModel]] = relationship(
        "DocumentChunkModel",
        back_populates="document",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class DocumentVersionModel(Base):
    """Immutable document version database entity."""

    __tablename__ = "document_versions"
    __table_args__ = (
        UniqueConstraint(
            "document_id", "version_number", name="uq_document_versions_document_version"
        ),
        Index("ix_document_versions_owner_checksum", "owner_id", "checksum_sha256"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    document_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    file_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    storage_key: Mapped[str] = mapped_column(String(512), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    document: Mapped[DocumentModel] = relationship("DocumentModel", back_populates="versions")
    chunks: Mapped[list[DocumentChunkModel]] = relationship(
        "DocumentChunkModel",
        back_populates="document_version",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
