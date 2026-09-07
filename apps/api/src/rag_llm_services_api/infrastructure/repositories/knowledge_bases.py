"""Repository for knowledge bases with owner tenancy enforcement."""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from rag_llm_services_api.db.models.knowledge_base import KnowledgeBaseModel


class KnowledgeBaseRepository:
    """Async repository for knowledge bases scoped to an owner."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        owner_id: UUID,
        name: str,
        description: str | None = None,
    ) -> KnowledgeBaseModel:
        """Create a new knowledge base for the owner."""
        kb = KnowledgeBaseModel(
            owner_id=owner_id,
            name=name,
            description=description,
        )
        self._session.add(kb)
        await self._session.flush()
        await self._session.refresh(kb)
        return kb

    async def get_by_id(
        self,
        owner_id: UUID,
        kb_id: UUID,
    ) -> KnowledgeBaseModel | None:
        """Fetch a knowledge base by ID, scoped to owner."""
        stmt = select(KnowledgeBaseModel).where(
            KnowledgeBaseModel.id == kb_id,
            KnowledgeBaseModel.owner_id == owner_id,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_name(
        self,
        owner_id: UUID,
        name: str,
    ) -> KnowledgeBaseModel | None:
        """Fetch a knowledge base by name, scoped to owner."""
        stmt = select(KnowledgeBaseModel).where(
            KnowledgeBaseModel.name == name,
            KnowledgeBaseModel.owner_id == owner_id,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list(
        self,
        owner_id: UUID,
        skip: int = 0,
        limit: int = 50,
    ) -> Sequence[KnowledgeBaseModel]:
        """List knowledge bases for the owner ordered by creation date."""
        stmt = (
            select(KnowledgeBaseModel)
            .where(KnowledgeBaseModel.owner_id == owner_id)
            .order_by(KnowledgeBaseModel.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def update(
        self,
        owner_id: UUID,
        kb_id: UUID,
        name: str | None = None,
        description: str | None = None,
    ) -> KnowledgeBaseModel | None:
        """Update an existing knowledge base."""
        kb = await self.get_by_id(owner_id, kb_id)
        if kb is None:
            return None
        if name is not None:
            kb.name = name
        if description is not None:
            kb.description = description
        await self._session.flush()
        await self._session.refresh(kb)
        return kb

    async def delete(
        self,
        owner_id: UUID,
        kb_id: UUID,
    ) -> bool:
        """Delete a knowledge base by ID, returning True if deleted."""
        stmt = (
            delete(KnowledgeBaseModel)
            .where(
                KnowledgeBaseModel.id == kb_id,
                KnowledgeBaseModel.owner_id == owner_id,
            )
            .returning(KnowledgeBaseModel.id)
        )
        result = await self._session.execute(stmt)
        deleted_id = result.scalar_one_or_none()
        return deleted_id is not None

    async def get_storage_keys_for_kb(self, owner_id: UUID, kb_id: UUID) -> Sequence[str]:
        """Retrieve all object storage keys for documents under a knowledge base."""
        from rag_llm_services_api.db.models.document import DocumentModel, DocumentVersionModel

        stmt = (
            select(DocumentVersionModel.storage_key)
            .join(DocumentModel, DocumentVersionModel.document_id == DocumentModel.id)
            .where(
                DocumentModel.knowledge_base_id == kb_id,
                DocumentModel.owner_id == owner_id,
            )
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()
