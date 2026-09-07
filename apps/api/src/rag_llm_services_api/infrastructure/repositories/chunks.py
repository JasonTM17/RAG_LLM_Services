"""Repository for document chunks with transactional replacement for idempotent re-indexing."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from rag_llm_services_api.db.models.document_chunk import DocumentChunkModel


@dataclass(frozen=True)
class ChunkCreateData:
    """Input data for creating a document chunk."""

    chunk_index: int
    content: str
    token_count: int
    metadata_json: dict[str, Any]
    embedding: list[float] | None = None


class ChunkRepository:
    """Repository managing document chunk persistence and transactional re-indexing."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def replace_document_chunks_transactionally(
        self,
        owner_id: UUID,
        document_id: UUID,
        document_version_id: UUID,
        chunks_data: list[ChunkCreateData],
    ) -> list[DocumentChunkModel]:
        """Atomically replace all chunks for a document version.

        Deletes existing chunks for the given version and inserts new ones within the
        same transaction to guarantee idempotent re-indexing without duplicate records.
        """
        # 1. Delete existing chunks for this version
        delete_stmt = delete(DocumentChunkModel).where(
            DocumentChunkModel.owner_id == owner_id,
            DocumentChunkModel.document_version_id == document_version_id,
        )
        await self._session.execute(delete_stmt)

        # 2. Insert new chunks
        new_chunk_models: list[DocumentChunkModel] = []
        for c in chunks_data:
            model = DocumentChunkModel(
                id=uuid.uuid4(),
                owner_id=owner_id,
                document_id=document_id,
                document_version_id=document_version_id,
                chunk_index=c.chunk_index,
                content=c.content,
                token_count=c.token_count,
                metadata_json=c.metadata_json,
                embedding=c.embedding,
            )
            new_chunk_models.append(model)

        if new_chunk_models:
            self._session.add_all(new_chunk_models)

        await self._session.flush()
        return new_chunk_models

    async def get_chunks_by_version(
        self,
        owner_id: UUID,
        document_version_id: UUID,
    ) -> Sequence[DocumentChunkModel]:
        """Fetch all chunks for a document version ordered by chunk_index."""
        stmt = (
            select(DocumentChunkModel)
            .where(
                DocumentChunkModel.owner_id == owner_id,
                DocumentChunkModel.document_version_id == document_version_id,
            )
            .order_by(DocumentChunkModel.chunk_index.asc())
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def get_chunks_by_document(
        self,
        owner_id: UUID,
        document_id: UUID,
    ) -> Sequence[DocumentChunkModel]:
        """Fetch all chunks for a document ordered by chunk_index."""
        stmt = (
            select(DocumentChunkModel)
            .where(
                DocumentChunkModel.owner_id == owner_id,
                DocumentChunkModel.document_id == document_id,
            )
            .order_by(DocumentChunkModel.chunk_index.asc())
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def count_chunks_by_version(
        self,
        owner_id: UUID,
        document_version_id: UUID,
    ) -> int:
        """Count total chunks stored for a document version."""
        stmt = select(func.count(DocumentChunkModel.id)).where(
            DocumentChunkModel.owner_id == owner_id,
            DocumentChunkModel.document_version_id == document_version_id,
        )
        result = await self._session.execute(stmt)
        return int(result.scalar_one())
