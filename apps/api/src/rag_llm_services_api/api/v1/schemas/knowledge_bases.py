"""Pydantic schemas for knowledge bases."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class KnowledgeBaseCreate(BaseModel):
    """Payload for creating a new knowledge base."""

    name: str = Field(..., min_length=1, max_length=255, description="Knowledge base name")
    description: str | None = Field(
        default=None, max_length=4096, description="Optional description"
    )


class KnowledgeBaseUpdate(BaseModel):
    """Payload for updating an existing knowledge base."""

    name: str | None = Field(default=None, min_length=1, max_length=255, description="Updated name")
    description: str | None = Field(
        default=None, max_length=4096, description="Updated description"
    )


class KnowledgeBaseResponse(BaseModel):
    """Response payload for a knowledge base."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    owner_id: UUID
    name: str
    description: str | None = None
    created_at: datetime
    updated_at: datetime
