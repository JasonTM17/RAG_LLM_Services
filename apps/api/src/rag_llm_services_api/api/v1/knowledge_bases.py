"""API router for knowledge bases."""

from __future__ import annotations

import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from rag_llm_services_api.api.dependencies.auth import get_current_user_id
from rag_llm_services_api.api.v1.schemas.knowledge_bases import (
    KnowledgeBaseCreate,
    KnowledgeBaseResponse,
    KnowledgeBaseUpdate,
)
from rag_llm_services_api.core.errors import ConflictError, NotFoundError
from rag_llm_services_api.db.session import get_session
from rag_llm_services_api.infrastructure.repositories.knowledge_bases import KnowledgeBaseRepository
from rag_llm_services_api.infrastructure.storage.base import ObjectStoragePort
from rag_llm_services_api.infrastructure.storage.minio import get_object_storage

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/knowledge-bases", tags=["knowledge-bases"])


@router.post(
    "",
    response_model=KnowledgeBaseResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new knowledge base",
)
async def create_knowledge_base(
    payload: KnowledgeBaseCreate,
    owner_id: Annotated[UUID, Depends(get_current_user_id)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> KnowledgeBaseResponse:
    """Create a new knowledge base scoped to the authenticated owner."""
    repo = KnowledgeBaseRepository(session)
    existing = await repo.get_by_name(owner_id, payload.name)
    if existing is not None:
        raise ConflictError(
            f"Knowledge base with name '{payload.name}' already exists",
            code="DUPLICATE_KNOWLEDGE_BASE",
        )

    try:
        kb = await repo.create(owner_id, payload.name, payload.description)
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise ConflictError(
            f"Knowledge base with name '{payload.name}' already exists",
            code="DUPLICATE_KNOWLEDGE_BASE",
        ) from exc
    return KnowledgeBaseResponse.model_validate(kb)


@router.get(
    "",
    response_model=list[KnowledgeBaseResponse],
    summary="List knowledge bases",
)
async def list_knowledge_bases(
    owner_id: Annotated[UUID, Depends(get_current_user_id)],
    session: Annotated[AsyncSession, Depends(get_session)],
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> list[KnowledgeBaseResponse]:
    """List all knowledge bases belonging to the authenticated owner."""
    repo = KnowledgeBaseRepository(session)
    kbs = await repo.list(owner_id, skip=skip, limit=limit)
    return [KnowledgeBaseResponse.model_validate(kb) for kb in kbs]


@router.get(
    "/{kb_id}",
    response_model=KnowledgeBaseResponse,
    summary="Get knowledge base details",
)
async def get_knowledge_base(
    kb_id: UUID,
    owner_id: Annotated[UUID, Depends(get_current_user_id)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> KnowledgeBaseResponse:
    """Get a knowledge base by ID scoped to the authenticated owner."""
    repo = KnowledgeBaseRepository(session)
    kb = await repo.get_by_id(owner_id, kb_id)
    if kb is None:
        raise NotFoundError("Knowledge base not found")
    return KnowledgeBaseResponse.model_validate(kb)


@router.patch(
    "/{kb_id}",
    response_model=KnowledgeBaseResponse,
    summary="Update knowledge base",
)
async def update_knowledge_base(
    kb_id: UUID,
    payload: KnowledgeBaseUpdate,
    owner_id: Annotated[UUID, Depends(get_current_user_id)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> KnowledgeBaseResponse:
    """Update knowledge base details."""
    repo = KnowledgeBaseRepository(session)
    if payload.name is not None:
        existing = await repo.get_by_name(owner_id, payload.name)
        if existing is not None and existing.id != kb_id:
            raise ConflictError(
                f"Knowledge base with name '{payload.name}' already exists",
                code="DUPLICATE_KNOWLEDGE_BASE",
            )

    try:
        kb = await repo.update(owner_id, kb_id, payload.name, payload.description)
        if kb is None:
            raise NotFoundError("Knowledge base not found")
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise ConflictError(
            f"Knowledge base with name '{payload.name}' already exists",
            code="DUPLICATE_KNOWLEDGE_BASE",
        ) from exc
    return KnowledgeBaseResponse.model_validate(kb)


@router.delete(
    "/{kb_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete knowledge base",
)
async def delete_knowledge_base(
    kb_id: UUID,
    owner_id: Annotated[UUID, Depends(get_current_user_id)],
    session: Annotated[AsyncSession, Depends(get_session)],
    storage: Annotated[ObjectStoragePort, Depends(get_object_storage)],
) -> None:
    """Delete knowledge base, cascade all associated records, and purge storage objects."""
    repo = KnowledgeBaseRepository(session)
    kb = await repo.get_by_id(owner_id, kb_id)
    if kb is None:
        raise NotFoundError("Knowledge base not found")

    storage_keys = await repo.get_storage_keys_for_kb(owner_id, kb_id)
    deleted = await repo.delete(owner_id, kb_id)
    if not deleted:
        raise NotFoundError("Knowledge base not found")
    await session.commit()

    for key in storage_keys:
        try:
            await storage.delete_object(key)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to delete storage object '%s' during KB cleanup: %s", key, exc)
