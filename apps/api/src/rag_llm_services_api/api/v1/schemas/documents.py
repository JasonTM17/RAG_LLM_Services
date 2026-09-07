"""Pydantic schemas for documents, versions, and ingestion jobs."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class DocumentVersionResponse(BaseModel):
    """Metadata for a specific version of a document."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    version_number: int
    file_size_bytes: int
    checksum_sha256: str
    mime_type: str
    created_at: datetime


class DocumentResponse(BaseModel):
    """Summary document metadata."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    owner_id: UUID
    knowledge_base_id: UUID
    filename: str
    content_type: str
    status: str
    error_message: str | None = None
    current_version_id: UUID | None = None
    created_at: datetime
    updated_at: datetime


class DocumentDetailResponse(DocumentResponse):
    """Detailed document metadata with versions list."""

    versions: list[DocumentVersionResponse] = Field(default_factory=list)


class DocumentUploadResponse(BaseModel):
    """Immediate response returned after successful document upload."""

    document_id: UUID
    version_id: UUID
    ingestion_job_id: UUID
    queue_task_id: str | None = None
    queued: bool = False
    filename: str
    status: str
    file_size_bytes: int
    checksum_sha256: str
    created_at: datetime


class IngestionJobResponse(BaseModel):
    """Metadata and status of an ingestion job."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    owner_id: UUID
    document_id: UUID
    document_version_id: UUID
    status: str
    error_message: str | None = None
    attempt_count: int = 0
    queued_task_id: str | None = None
    created_at: datetime
    updated_at: datetime


class QueueStatusResponse(BaseModel):
    """Approximate queue status for ingestion workers."""

    queue_name: str
    depth: int
