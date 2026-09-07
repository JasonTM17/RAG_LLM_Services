"""Domain models and enums for document management and storage."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

ALLOWED_MIME_TYPES = frozenset(
    {
        "application/pdf",
        "text/plain",
        "text/markdown",
        "text/x-markdown",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }
)

ALLOWED_EXTENSIONS = frozenset({".pdf", ".txt", ".md", ".docx"})

# 50 MB maximum document size
DEFAULT_MAX_UPLOAD_SIZE_BYTES = 50 * 1024 * 1024


class DocumentStatus(StrEnum):
    """Stable lifecycle statuses for documents."""

    UPLOADED = "UPLOADED"
    PARSING = "PARSING"
    CHUNKING = "CHUNKING"
    EMBEDDING = "EMBEDDING"
    INDEXED = "INDEXED"
    FAILED = "FAILED"


class IngestionJobStatus(StrEnum):
    """Stable lifecycle statuses for ingestion jobs."""

    PENDING = "PENDING"
    PARSING = "PARSING"
    CHUNKING = "CHUNKING"
    EMBEDDING = "EMBEDDING"
    INDEXED = "INDEXED"
    FAILED = "FAILED"


@dataclass(frozen=True)
class Document:
    """Document entity tracking document metadata."""

    id: UUID
    owner_id: UUID
    knowledge_base_id: UUID
    filename: str
    content_type: str
    status: DocumentStatus
    error_message: str | None = None
    current_version_id: UUID | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True)
class DocumentVersion:
    """Immutable version of an uploaded document file."""

    id: UUID
    owner_id: UUID
    document_id: UUID
    version_number: int
    file_size_bytes: int
    checksum_sha256: str
    storage_key: str
    mime_type: str
    created_at: datetime | None = None


@dataclass(frozen=True)
class IngestionJob:
    """Asynchronous ingestion job entity."""

    id: UUID
    owner_id: UUID
    document_id: UUID
    document_version_id: UUID
    status: IngestionJobStatus
    error_message: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
