"""Domain models for knowledge bases."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True)
class KnowledgeBase:
    """Knowledge base domain model representing an isolated collection of documents."""

    id: UUID
    owner_id: UUID
    name: str
    description: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
