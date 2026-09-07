"""Repository for documents, versions, and ingestion jobs with owner tenancy."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from rag_llm_services_api.db.models.document import DocumentModel, DocumentVersionModel
from rag_llm_services_api.db.models.ingestion_job import IngestionJobModel
from rag_llm_services_api.domain.documents import DocumentStatus, IngestionJobStatus


class DocumentRepository:
    """Async repository for documents, document versions, and ingestion jobs."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def find_version_by_checksum(
        self,
        owner_id: UUID,
        knowledge_base_id: UUID,
        checksum_sha256: str,
    ) -> DocumentVersionModel | None:
        """Check whether a document version with this checksum exists in the knowledge base."""
        stmt = (
            select(DocumentVersionModel)
            .join(DocumentModel, DocumentVersionModel.document_id == DocumentModel.id)
            .where(
                DocumentModel.knowledge_base_id == knowledge_base_id,
                DocumentModel.owner_id == owner_id,
                DocumentVersionModel.checksum_sha256 == checksum_sha256,
            )
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def create_document_with_version_and_job(
        self,
        owner_id: UUID,
        knowledge_base_id: UUID,
        filename: str,
        content_type: str,
        file_size_bytes: int,
        checksum_sha256: str,
        storage_key: str,
        document_id: UUID | None = None,
        version_id: UUID | None = None,
        job_id: UUID | None = None,
    ) -> tuple[DocumentModel, DocumentVersionModel, IngestionJobModel]:
        """Atomically create a Document, its initial DocumentVersion, and an IngestionJob."""
        doc_id = document_id or uuid.uuid4()
        ver_id = version_id or uuid.uuid4()
        j_id = job_id or uuid.uuid4()

        document = DocumentModel(
            id=doc_id,
            owner_id=owner_id,
            knowledge_base_id=knowledge_base_id,
            filename=filename,
            content_type=content_type,
            status=DocumentStatus.UPLOADED.value,
            current_version_id=ver_id,
        )
        version = DocumentVersionModel(
            id=ver_id,
            owner_id=owner_id,
            document_id=doc_id,
            version_number=1,
            file_size_bytes=file_size_bytes,
            checksum_sha256=checksum_sha256,
            storage_key=storage_key,
            mime_type=content_type,
        )
        job = IngestionJobModel(
            id=j_id,
            owner_id=owner_id,
            document_id=doc_id,
            document_version_id=ver_id,
            status=IngestionJobStatus.PENDING.value,
        )

        self._session.add_all([document, version, job])
        await self._session.flush()
        await self._session.refresh(document)
        await self._session.refresh(version)
        await self._session.refresh(job)
        return document, version, job

    async def get_document_by_id(
        self,
        owner_id: UUID,
        doc_id: UUID,
    ) -> DocumentModel | None:
        """Fetch document by ID with versions preloaded, scoped to owner."""
        stmt = (
            select(DocumentModel)
            .options(selectinload(DocumentModel.versions))
            .where(
                DocumentModel.id == doc_id,
                DocumentModel.owner_id == owner_id,
            )
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_documents(
        self,
        owner_id: UUID,
        knowledge_base_id: UUID | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> Sequence[DocumentModel]:
        """List documents for the owner, optionally filtered by knowledge base."""
        stmt = (
            select(DocumentModel)
            .options(selectinload(DocumentModel.versions))
            .where(DocumentModel.owner_id == owner_id)
        )
        if knowledge_base_id is not None:
            stmt = stmt.where(DocumentModel.knowledge_base_id == knowledge_base_id)
        stmt = stmt.order_by(DocumentModel.created_at.desc()).offset(skip).limit(limit)

        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def delete_document(
        self,
        owner_id: UUID,
        doc_id: UUID,
    ) -> list[str] | None:
        """Delete document and return associated storage keys for MinIO cleanup, or None if not found."""
        doc = await self.get_document_by_id(owner_id, doc_id)
        if doc is None:
            return None
        storage_keys = [ver.storage_key for ver in doc.versions]
        await self._session.delete(doc)
        await self._session.flush()
        return storage_keys

    async def create_ingestion_job(
        self,
        owner_id: UUID,
        document_id: UUID,
        version_id: UUID,
    ) -> IngestionJobModel:
        """Create a new ingestion job for reindexing."""
        job = IngestionJobModel(
            owner_id=owner_id,
            document_id=document_id,
            document_version_id=version_id,
            status=IngestionJobStatus.PENDING.value,
        )
        self._session.add(job)
        await self._session.flush()
        await self._session.refresh(job)
        return job

    async def get_ingestion_job(
        self,
        owner_id: UUID,
        job_id: UUID,
    ) -> IngestionJobModel | None:
        """Fetch an ingestion job by ID, scoped to owner."""
        stmt = select(IngestionJobModel).where(
            IngestionJobModel.id == job_id,
            IngestionJobModel.owner_id == owner_id,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def update_document_status(
        self,
        owner_id: UUID,
        doc_id: UUID,
        status: str,
        error_message: str | None = None,
    ) -> DocumentModel | None:
        """Update a document's status and optional error message."""
        doc = await self.get_document_by_id(owner_id, doc_id)
        if doc is None:
            return None
        doc.status = status
        doc.error_message = error_message
        await self._session.flush()
        await self._session.refresh(doc)
        return doc

    async def update_ingestion_job_status(
        self,
        owner_id: UUID,
        job_id: UUID,
        status: str,
        error_message: str | None = None,
    ) -> IngestionJobModel | None:
        """Update an ingestion job's status and optional error message."""
        job = await self.get_ingestion_job(owner_id, job_id)
        if job is None:
            return None
        job.status = status
        job.error_message = error_message
        await self._session.flush()
        await self._session.refresh(job)
        return job
