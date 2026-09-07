"""Pydantic schemas for the retrieval search API."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from rag_llm_services_rag.retrieval.types import RetrievalFilter, RetrievalMethod


class RetrievalFilterSchema(BaseModel):
    """Optional metadata filters for search queries."""

    model_config = ConfigDict(from_attributes=True)

    knowledge_base_id: UUID | None = None
    document_ids: list[UUID] | None = None
    mime_types: list[str] | None = None
    page: int | None = Field(default=None, ge=1)
    section: str | None = Field(default=None, min_length=1, max_length=255)
    created_after: datetime | None = None
    created_before: datetime | None = None
    metadata: dict[str, Any] | None = None

    def to_domain(self) -> RetrievalFilter:
        """Convert API schema to retrieval domain filter."""
        return RetrievalFilter(
            knowledge_base_id=self.knowledge_base_id,
            document_ids=self.document_ids,
            mime_types=self.mime_types,
            page=self.page,
            section=self.section,
            created_after=self.created_after,
            created_before=self.created_before,
            metadata=self.metadata,
        )


class RetrievalSearchRequest(BaseModel):
    """Search request body for POST /api/v1/retrieval/search."""

    query: str = Field(..., min_length=1, max_length=2000, description="Search query string")
    method: RetrievalMethod = Field(
        default=RetrievalMethod.HYBRID,
        description="Retrieval method strategy (vector, keyword, hybrid)",
    )
    filter: RetrievalFilterSchema | None = Field(
        default=None,
        description="Scoping filters by knowledge base, documents, mime types, page, section, date, or metadata",
    )
    vector_top_k: int | None = Field(
        default=None, ge=1, le=100, description="Top-k candidates from vector search"
    )
    keyword_top_k: int | None = Field(
        default=None, ge=1, le=100, description="Top-k candidates from keyword search"
    )
    rerank_top_k: int | None = Field(
        default=None, ge=1, le=50, description="Top-k candidates after reranking"
    )
    context_token_budget: int | None = Field(
        default=None,
        ge=100,
        le=32000,
        description="Max token budget for context bundle assembly",
    )
    include_context_bundle: bool = Field(
        default=True,
        description="Whether to assemble and return a source-labeled ContextBundle",
    )


class RetrievalChunkResponse(BaseModel):
    """A ranked chunk candidate returned by search."""

    model_config = ConfigDict(from_attributes=True)

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
    metadata: dict[str, Any] = Field(default_factory=dict)


class CitedChunkResponse(BaseModel):
    """A citation source chunk included in the ContextBundle."""

    model_config = ConfigDict(from_attributes=True)

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
    metadata: dict[str, Any] = Field(default_factory=dict)


class ContextBundleResponse(BaseModel):
    """Source-labeled context bundle formatted with citation identifiers."""

    model_config = ConfigDict(from_attributes=True)

    context_text: str
    cited_chunks: list[CitedChunkResponse] = Field(default_factory=list)
    total_tokens: int = 0
    total_chunks: int = 0
    max_budget: int = 6000


class RetrievalSearchResponse(BaseModel):
    """Response payload for POST /api/v1/retrieval/search."""

    model_config = ConfigDict(from_attributes=True)

    query: str
    retrieval_method: RetrievalMethod
    results: list[RetrievalChunkResponse] = Field(default_factory=list)
    context_bundle: ContextBundleResponse | None = None
    latency_ms: float = 0.0
    stage_latencies_ms: dict[str, float] = Field(default_factory=dict)
    total_results: int = 0
