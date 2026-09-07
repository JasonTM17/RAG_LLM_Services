"""API router for document management, uploads, downloads, and lifecycle."""

from __future__ import annotations

import io
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from rag_llm_services_api.api.dependencies.auth import get_current_user_id
from rag_llm_services_api.api.v1.schemas.documents import (
    DocumentDetailResponse,
    DocumentResponse,
    DocumentUploadResponse,
    DocumentVersionResponse,
    IngestionJobResponse,
)
from rag_llm_services_api.application.document_service import DocumentApplicationService
from rag_llm_services_api.core.errors import ValidationError
from rag_llm_services_api.db.session import get_session
from rag_llm_services_api.infrastructure.repositories.documents import DocumentRepository
from rag_llm_services_api.infrastructure.repositories.knowledge_bases import KnowledgeBaseRepository
from rag_llm_services_api.infrastructure.storage.base import ObjectStoragePort
from rag_llm_services_api.infrastructure.storage.minio import get_object_storage

router = APIRouter(prefix="/documents", tags=["documents"])


def get_document_service(
    session: Annotated[AsyncSession, Depends(get_session)],
    storage: Annotated[ObjectStoragePort, Depends(get_object_storage)],
) -> DocumentApplicationService:
    """Dependency assembling the DocumentApplicationService."""
    doc_repo = DocumentRepository(session)
    kb_repo = KnowledgeBaseRepository(session)
    return DocumentApplicationService(
        document_repo=doc_repo,
        knowledge_base_repo=kb_repo,
        storage=storage,
    )


@router.post(
    "",
    response_model=DocumentUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a new document",
)
async def upload_document(
    file: Annotated[UploadFile, File(description="Document binary file (PDF, TXT, MD, DOCX)")],
    knowledge_base_id: Annotated[UUID, Form(description="Target knowledge base ID")],
    owner_id: Annotated[UUID, Depends(get_current_user_id)],
    session: Annotated[AsyncSession, Depends(get_session)],
    service: Annotated[DocumentApplicationService, Depends(get_document_service)],
) -> DocumentUploadResponse:
    """Upload a document, validate MIME, compute checksum, store in MinIO, and enqueue ingestion."""
    if not file.filename:
        raise ValidationError("Uploaded file must have a filename", code="INVALID_FILENAME")

    content = await file.read()
    doc, version, job = await service.upload_document(
        owner_id=owner_id,
        knowledge_base_id=knowledge_base_id,
        raw_filename=file.filename,
        content=content,
    )
    await session.commit()

    assert doc.created_at is not None, "Created timestamp must be populated"

    return DocumentUploadResponse(
        document_id=doc.id,
        version_id=version.id,
        ingestion_job_id=job.id,
        filename=doc.filename,
        status=doc.status,
        file_size_bytes=version.file_size_bytes,
        checksum_sha256=version.checksum_sha256,
        created_at=doc.created_at,
    )


@router.get(
    "",
    response_model=list[DocumentResponse],
    summary="List documents",
)
async def list_documents(
    owner_id: Annotated[UUID, Depends(get_current_user_id)],
    session: Annotated[AsyncSession, Depends(get_session)],
    knowledge_base_id: Annotated[UUID | None, Query(description="Filter by knowledge base")] = None,
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> list[DocumentResponse]:
    """List documents for the authenticated owner."""
    repo = DocumentRepository(session)
    docs = await repo.list_documents(
        owner_id=owner_id,
        knowledge_base_id=knowledge_base_id,
        skip=skip,
        limit=limit,
    )
    return [DocumentResponse.model_validate(doc) for doc in docs]


@router.get(
    "/{document_id}",
    response_model=DocumentDetailResponse,
    summary="Get document details",
)
async def get_document(
    document_id: UUID,
    owner_id: Annotated[UUID, Depends(get_current_user_id)],
    service: Annotated[DocumentApplicationService, Depends(get_document_service)],
) -> DocumentDetailResponse:
    """Get document details with versions list."""
    doc = await service.get_document(owner_id, document_id)
    versions = [DocumentVersionResponse.model_validate(v) for v in (doc.versions or [])]
    return DocumentDetailResponse(
        id=doc.id,
        owner_id=doc.owner_id,
        knowledge_base_id=doc.knowledge_base_id,
        filename=doc.filename,
        content_type=doc.content_type,
        status=doc.status,
        error_message=doc.error_message,
        current_version_id=doc.current_version_id,
        created_at=doc.created_at,
        updated_at=doc.updated_at,
        versions=versions,
    )


@router.get(
    "/{document_id}/download",
    summary="Download raw document file",
)
async def download_document(
    document_id: UUID,
    owner_id: Annotated[UUID, Depends(get_current_user_id)],
    service: Annotated[DocumentApplicationService, Depends(get_document_service)],
) -> StreamingResponse:
    """Download the raw file bytes of the document's current version."""
    content_bytes, content_type, filename = await service.get_document_content(
        owner_id, document_id
    )
    return StreamingResponse(
        io.BytesIO(content_bytes),
        media_type=content_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.delete(
    "/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete document",
)
async def delete_document(
    document_id: UUID,
    owner_id: Annotated[UUID, Depends(get_current_user_id)],
    session: Annotated[AsyncSession, Depends(get_session)],
    service: Annotated[DocumentApplicationService, Depends(get_document_service)],
) -> None:
    """Delete document from database and remove associated raw objects from MinIO."""
    await service.delete_document(owner_id, document_id)
    await session.commit()


@router.post(
    "/{document_id}/reindex",
    response_model=IngestionJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger document reindexing",
)
async def reindex_document(
    document_id: UUID,
    owner_id: Annotated[UUID, Depends(get_current_user_id)],
    session: Annotated[AsyncSession, Depends(get_session)],
    service: Annotated[DocumentApplicationService, Depends(get_document_service)],
) -> IngestionJobResponse:
    """Create a new ingestion job to reindex the document."""
    job = await service.reindex_document(owner_id, document_id)
    await session.commit()
    return IngestionJobResponse.model_validate(job)
