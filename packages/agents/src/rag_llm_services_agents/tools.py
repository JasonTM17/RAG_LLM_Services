"""Typed, bounded knowledge-base tools exposed to agents."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from rag_llm_services_rag.retrieval.types import (
    CitedChunk,
    ContextBundle,
    RetrievalFilter,
    RetrievalMethod,
)


class AgentToolScopeError(ValueError):
    """Raised when a tool request resolves outside the server-controlled owner scope."""


class AgentToolLimits(BaseModel):
    """Size and count limits for tool inputs and outputs."""

    model_config = ConfigDict(frozen=True)

    max_results: int = Field(default=5, ge=1, le=20)
    max_context_chunks: int = Field(default=5, ge=1, le=20)
    max_chunk_chars: int = Field(default=1200, ge=200, le=4000)
    max_context_chars: int = Field(default=6000, ge=1000, le=24000)
    max_documents: int = Field(default=20, ge=1, le=100)


class SearchKnowledgeBaseInput(BaseModel):
    """Input for search_knowledge_base."""

    query: str = Field(..., min_length=1, max_length=2000)
    knowledge_base_id: UUID | None = None
    top_k: int = Field(default=5, ge=1, le=20)
    context_token_budget: int | None = Field(default=None, ge=100, le=32000)


class DocumentContextInput(BaseModel):
    """Input for get_document_context."""

    document_id: UUID
    query: str = Field(default="document context", min_length=1, max_length=2000)
    max_chunks: int = Field(default=5, ge=1, le=20)
    context_token_budget: int | None = Field(default=None, ge=100, le=32000)


class DocumentListInput(BaseModel):
    """Input for list_documents."""

    knowledge_base_id: UUID | None = None
    limit: int = Field(default=20, ge=1, le=100)


class SourceChunk(BaseModel):
    """Source-labeled chunk returned by a bounded tool call."""

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

    @classmethod
    def from_cited_chunk(cls, chunk: CitedChunk, *, max_chars: int) -> SourceChunk:
        return cls(
            source_id=chunk.source_id,
            chunk_id=chunk.chunk_id,
            document_id=chunk.document_id,
            content=_truncate(chunk.content, max_chars),
            filename=chunk.filename,
            page=chunk.page,
            section=chunk.section,
            token_count=chunk.token_count,
            score=chunk.score,
            retrieval_method=chunk.retrieval_method,
            metadata=dict(chunk.metadata),
        )

    def to_cited_chunk(self) -> CitedChunk:
        return CitedChunk(
            source_id=self.source_id,
            chunk_id=self.chunk_id,
            document_id=self.document_id,
            content=self.content,
            filename=self.filename,
            page=self.page,
            section=self.section,
            token_count=self.token_count,
            score=self.score,
            retrieval_method=self.retrieval_method,
            metadata=dict(self.metadata),
        )


class KnowledgeBaseSearchOutput(BaseModel):
    """Bounded source context returned by a knowledge-base tool."""

    context_text: str
    sources: list[SourceChunk] = Field(default_factory=list)
    total_tokens: int = 0
    total_chunks: int = 0
    max_budget: int = 0

    def to_context_bundle(self) -> ContextBundle:
        return ContextBundle(
            context_text=self.context_text,
            cited_chunks=[source.to_cited_chunk() for source in self.sources],
            total_tokens=self.total_tokens,
            total_chunks=self.total_chunks,
            max_budget=self.max_budget,
        )


class DocumentMetadata(BaseModel):
    """Document metadata exposed to agents without raw object storage details."""

    id: UUID
    knowledge_base_id: UUID
    filename: str
    content_type: str
    status: str
    created_at: datetime | None = None
    updated_at: datetime | None = None
    current_version_id: UUID | None = None


class RetrievalPort(Protocol):
    """Application-layer retrieval surface consumed by agent tools."""

    async def search(
        self,
        owner_id: UUID,
        query: str,
        method: RetrievalMethod = RetrievalMethod.HYBRID,
        filter: RetrievalFilter | None = None,
        vector_top_k: int | None = None,
        keyword_top_k: int | None = None,
        rerank_top_k: int | None = None,
        context_token_budget: int | None = None,
        include_context_bundle: bool = True,
    ) -> Any: ...


class DocumentCatalogPort(Protocol):
    """Application-layer document catalog surface consumed by agent tools."""

    async def list_documents(
        self,
        *,
        owner_id: UUID,
        knowledge_base_id: UUID | None,
        limit: int,
    ) -> Sequence[DocumentMetadata]: ...

    async def get_document_metadata(
        self,
        *,
        owner_id: UUID,
        document_id: UUID,
    ) -> DocumentMetadata | None: ...


class KnowledgeBaseTools:
    """Knowledge tools with server-side owner scope and bounded outputs."""

    def __init__(
        self,
        *,
        retrieval_service: RetrievalPort,
        document_catalog: DocumentCatalogPort,
        limits: AgentToolLimits | None = None,
    ) -> None:
        self._retrieval_service = retrieval_service
        self._document_catalog = document_catalog
        self._limits = limits or AgentToolLimits()

    @property
    def limits(self) -> AgentToolLimits:
        return self._limits

    async def search_knowledge_base(
        self,
        *,
        owner_id: UUID,
        payload: SearchKnowledgeBaseInput,
    ) -> KnowledgeBaseSearchOutput:
        """Search owner-scoped knowledge bases and return bounded cited context."""
        top_k = min(payload.top_k, self._limits.max_results)
        response = await self._retrieval_service.search(
            owner_id=owner_id,
            query=payload.query,
            method=RetrievalMethod.HYBRID,
            filter=RetrievalFilter(knowledge_base_id=payload.knowledge_base_id),
            vector_top_k=top_k,
            keyword_top_k=top_k,
            rerank_top_k=top_k,
            context_token_budget=payload.context_token_budget,
            include_context_bundle=True,
        )
        return _bound_context_bundle(
            response.context_bundle,
            limits=self._limits,
        )

    async def get_document_context(
        self,
        *,
        owner_id: UUID,
        payload: DocumentContextInput,
    ) -> KnowledgeBaseSearchOutput:
        """Retrieve bounded context for one owner-scoped document."""
        metadata = await self._document_catalog.get_document_metadata(
            owner_id=owner_id,
            document_id=payload.document_id,
        )
        if metadata is None:
            raise AgentToolScopeError("Document not found in owner scope")
        top_k = min(payload.max_chunks, self._limits.max_context_chunks)
        response = await self._retrieval_service.search(
            owner_id=owner_id,
            query=payload.query,
            method=RetrievalMethod.HYBRID,
            filter=RetrievalFilter(document_ids=[payload.document_id]),
            vector_top_k=top_k,
            keyword_top_k=top_k,
            rerank_top_k=top_k,
            context_token_budget=payload.context_token_budget,
            include_context_bundle=True,
        )
        return _bound_context_bundle(response.context_bundle, limits=self._limits)

    async def list_documents(
        self,
        *,
        owner_id: UUID,
        payload: DocumentListInput,
    ) -> list[DocumentMetadata]:
        """List owner-scoped documents for agent planning."""
        limit = min(payload.limit, self._limits.max_documents)
        documents = await self._document_catalog.list_documents(
            owner_id=owner_id,
            knowledge_base_id=payload.knowledge_base_id,
            limit=limit,
        )
        return list(documents)[:limit]

    async def get_document_metadata(
        self,
        *,
        owner_id: UUID,
        document_id: UUID,
    ) -> DocumentMetadata:
        """Fetch owner-scoped document metadata without raw object keys."""
        metadata = await self._document_catalog.get_document_metadata(
            owner_id=owner_id,
            document_id=document_id,
        )
        if metadata is None:
            raise AgentToolScopeError("Document not found in owner scope")
        return metadata


def _bound_context_bundle(
    bundle: ContextBundle | None,
    *,
    limits: AgentToolLimits,
) -> KnowledgeBaseSearchOutput:
    if bundle is None:
        return KnowledgeBaseSearchOutput(context_text="")
    bounded_sources = [
        SourceChunk.from_cited_chunk(chunk, max_chars=limits.max_chunk_chars)
        for chunk in bundle.cited_chunks[: limits.max_context_chunks]
    ]
    context_text = _truncate(bundle.context_text, limits.max_context_chars)
    return KnowledgeBaseSearchOutput(
        context_text=context_text,
        sources=bounded_sources,
        total_tokens=bundle.total_tokens,
        total_chunks=len(bounded_sources),
        max_budget=bundle.max_budget,
    )


def _truncate(value: str, max_chars: int) -> str:
    stripped = value.strip()
    if len(stripped) <= max_chars:
        return stripped
    marker = "\n[truncated]"
    return stripped[: max(0, max_chars - len(marker))].rstrip() + marker
