"""Domain types and data transfer objects for hybrid retrieval, reranking, and context selection."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID


class RetrievalMethod(str, Enum):
    """Retrieval execution strategy and provenance tagging."""

    VECTOR = "vector"
    KEYWORD = "keyword"
    HYBRID = "hybrid"

    @classmethod
    def _missing_(cls, value: object) -> Any:
        if isinstance(value, str):
            normalized = value.strip().lower()
            for member in cls:
                if member.value == normalized or member.name.lower() == normalized:
                    return member
        return super()._missing_(value)


@dataclass
class CandidateChunk:
    """A retrieved chunk candidate before or during fusion and reranking."""

    chunk_id: UUID
    document_id: UUID
    content: str
    score: float
    retrieval_method: RetrievalMethod
    document_version_id: UUID | None = None
    chunk_index: int = 0
    token_count: int = 0
    filename: str = ""
    page: int | None = None
    section: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class RetrievalResult:
    """A ranked chunk result produced by fusion or reranking."""

    chunk_id: UUID
    document_id: UUID
    content: str
    score: float
    retrieval_method: RetrievalMethod
    filename: str = ""
    page: int | None = None
    section: str | None = None
    chunk_index: int = 0
    token_count: int = 0
    rank: int = 1
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class CitedChunk:
    """A selected chunk assigned a source identifier [S1], [S2], etc. for LLM citations."""

    source_id: str
    chunk_id: UUID
    document_id: UUID
    content: str
    filename: str = ""
    page: int | None = None
    section: str | None = None
    token_count: int = 0
    score: float = 0.0
    retrieval_method: RetrievalMethod = RetrievalMethod.HYBRID
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ContextBundle:
    """Source-rich, token-bounded context ready for LLM consumption."""

    context_text: str
    cited_chunks: list[CitedChunk] = field(default_factory=list)
    total_tokens: int = 0
    total_chunks: int = 0
    max_budget: int = 6000


@dataclass
class RetrievalFilter:
    """Scoping criteria for vector and keyword search queries."""

    knowledge_base_id: UUID | None = None
    document_ids: list[UUID] | None = None
    mime_types: list[str] | None = None
    page: int | None = None
    section: str | None = None
    created_after: datetime | None = None
    created_before: datetime | None = None
    metadata: dict[str, Any] | None = None
