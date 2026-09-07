"""Keyword retriever performing full-text search with query normalization."""

from __future__ import annotations

import re
from typing import Any
from uuid import UUID

from rag_llm_services_rag.retrieval.query import QueryNormalizer
from rag_llm_services_rag.retrieval.types import (
    CandidateChunk,
    RetrievalFilter,
    RetrievalMethod,
)

_TOKEN_RE = re.compile(r"\w+")


def _metadata_value(chunk: dict[str, Any], *keys: str) -> Any:
    metadata = chunk.get("metadata", {})
    for key in keys:
        if key in chunk:
            return chunk[key]
        if isinstance(metadata, dict) and key in metadata:
            return metadata[key]
    return None


def _matches_filter(chunk: dict[str, Any], filter: RetrievalFilter | None) -> bool:
    if filter is None:
        return True
    if (
        filter.knowledge_base_id
        and _metadata_value(chunk, "knowledge_base_id") != filter.knowledge_base_id
    ):
        return False
    if filter.document_ids and chunk["document_id"] not in filter.document_ids:
        return False
    if (
        filter.mime_types
        and _metadata_value(chunk, "mime_type", "content_type") not in filter.mime_types
    ):
        return False
    if filter.page is not None:
        page = _metadata_value(chunk, "page", "page_number")
        if isinstance(page, str) and page.isdecimal():
            page = int(page)
        if page != filter.page:
            return False
    if filter.section and _metadata_value(chunk, "section", "section_header") != filter.section:
        return False
    created_at = _metadata_value(chunk, "created_at")
    if filter.created_after and created_at and created_at < filter.created_after:
        return False
    if filter.created_before and created_at and created_at > filter.created_before:
        return False
    if filter.metadata:
        metadata = chunk.get("metadata", {})
        if not isinstance(metadata, dict):
            return False
        if not all(metadata.get(k) == v for k, v in filter.metadata.items()):
            return False
    return True


class InMemoryKeywordBackend:
    """In-memory keyword search backend for standalone tests and verification."""

    def __init__(self, chunks: list[dict[str, Any]] | None = None) -> None:
        self.chunks: list[dict[str, Any]] = list(chunks or [])

    def add_chunk(
        self,
        chunk_id: UUID,
        document_id: UUID,
        content: str,
        owner_id: UUID,
        filename: str = "",
        page: int | None = None,
        section: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.chunks.append(
            {
                "chunk_id": chunk_id,
                "document_id": document_id,
                "content": content,
                "owner_id": owner_id,
                "filename": filename,
                "page": page,
                "section": section,
                "metadata": metadata or {},
            }
        )

    async def search_keyword(
        self,
        owner_id: UUID,
        query: str,
        top_k: int = 10,
        filter: RetrievalFilter | None = None,
    ) -> list[CandidateChunk]:
        query_terms = [t.lower() for t in _TOKEN_RE.findall(query)]
        if not query_terms:
            return []

        scored: list[tuple[float, dict[str, Any]]] = []
        for c in self.chunks:
            if c["owner_id"] != owner_id:
                continue
            if not _matches_filter(c, filter):
                continue

            content_lower = c["content"].lower()
            # Simple TF match score: count of matching terms
            matched_count = sum(content_lower.count(t) for t in query_terms)
            if matched_count > 0:
                # Score normalized by term count
                score = round(matched_count / (len(query_terms) + 1.0), 6)
                scored.append((score, c))

        scored.sort(key=lambda item: (-item[0], str(item[1]["chunk_id"])))
        scored = scored[:top_k]

        results: list[CandidateChunk] = []
        for score, c in scored:
            results.append(
                CandidateChunk(
                    chunk_id=c["chunk_id"],
                    document_id=c["document_id"],
                    content=c["content"],
                    score=score,
                    retrieval_method=RetrievalMethod.KEYWORD,
                    filename=c.get("filename", ""),
                    page=c.get("page"),
                    section=c.get("section"),
                    metadata=dict(c.get("metadata", {})),
                )
            )
        return results


class KeywordRetriever:
    """Retriever executing normalized full-text search against PostgreSQL or configured backend."""

    def __init__(
        self,
        search_backend: Any = None,
        normalizer: QueryNormalizer | None = None,
        default_top_k: int = 10,
    ) -> None:
        self._search_backend = search_backend or InMemoryKeywordBackend()
        self._normalizer = normalizer or QueryNormalizer()
        self._default_top_k = default_top_k

    async def retrieve(
        self,
        query: str,
        owner_id: UUID,
        filter: RetrievalFilter | None = None,
        top_k: int | None = None,
    ) -> list[CandidateChunk]:
        """Normalize query and execute lexical keyword search."""
        normalized_query = self._normalizer.normalize(query)
        if not normalized_query:
            return []

        limit = top_k if top_k is not None and top_k > 0 else self._default_top_k

        if hasattr(self._search_backend, "search_keyword"):
            candidates = await self._search_backend.search_keyword(
                owner_id=owner_id,
                query=normalized_query,
                top_k=limit,
                filter=filter,
            )
        elif callable(self._search_backend):
            candidates = await self._search_backend(
                normalized_query,
                owner_id,
                filter,
                limit,
            )
        else:
            raise TypeError(
                f"Unsupported keyword search backend type: {type(self._search_backend)}"
            )

        for c in candidates:
            c.retrieval_method = RetrievalMethod.KEYWORD

        return candidates
