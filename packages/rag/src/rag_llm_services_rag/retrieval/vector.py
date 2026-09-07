"""Vector retriever utilizing dense embeddings and similarity search."""

from __future__ import annotations

import math
from typing import Any
from uuid import UUID

from rag_llm_services_embeddings.base import EmbeddingProvider
from rag_llm_services_rag.retrieval.types import (
    CandidateChunk,
    RetrievalFilter,
    RetrievalMethod,
)


def cosine_similarity(v1: list[float], v2: list[float]) -> float:
    """Compute cosine similarity between two float vectors."""
    dot = sum(a * b for a, b in zip(v1, v2, strict=False))
    norm_v1 = math.sqrt(sum(a * a for a in v1))
    norm_v2 = math.sqrt(sum(b * b for b in v2))
    if norm_v1 == 0.0 or norm_v2 == 0.0:
        return 0.0
    return dot / (norm_v1 * norm_v2)


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


class InMemoryVectorBackend:
    """In-memory vector search backend for standalone tests and verification."""

    def __init__(self, chunks: list[dict[str, Any]] | None = None) -> None:
        self.chunks: list[dict[str, Any]] = list(chunks or [])

    def add_chunk(
        self,
        chunk_id: UUID,
        document_id: UUID,
        content: str,
        embedding: list[float],
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
                "embedding": embedding,
                "owner_id": owner_id,
                "filename": filename,
                "page": page,
                "section": section,
                "metadata": metadata or {},
            }
        )

    async def search_vector(
        self,
        owner_id: UUID,
        query_embedding: list[float],
        top_k: int = 10,
        filter: RetrievalFilter | None = None,
    ) -> list[CandidateChunk]:
        scored: list[tuple[float, dict[str, Any]]] = []
        for c in self.chunks:
            if c["owner_id"] != owner_id:
                continue
            if not _matches_filter(c, filter):
                continue

            sim = cosine_similarity(query_embedding, c["embedding"])
            scored.append((sim, c))

        scored.sort(key=lambda item: (-item[0], str(item[1]["chunk_id"])))
        scored = scored[:top_k]

        results: list[CandidateChunk] = []
        for sim, c in scored:
            results.append(
                CandidateChunk(
                    chunk_id=c["chunk_id"],
                    document_id=c["document_id"],
                    content=c["content"],
                    score=round(sim, 6),
                    retrieval_method=RetrievalMethod.VECTOR,
                    filename=c.get("filename", ""),
                    page=c.get("page"),
                    section=c.get("section"),
                    metadata=dict(c.get("metadata", {})),
                )
            )
        return results


class VectorRetriever:
    """Retriever generating query embeddings and retrieving candidate chunks via dense similarity."""

    def __init__(
        self,
        embedding_provider: EmbeddingProvider,
        search_backend: Any = None,
        default_top_k: int = 10,
    ) -> None:
        self._embedding_provider = embedding_provider
        self._search_backend = search_backend or InMemoryVectorBackend()
        self._default_top_k = default_top_k

    async def retrieve(
        self,
        query: str,
        owner_id: UUID,
        filter: RetrievalFilter | None = None,
        top_k: int | None = None,
    ) -> list[CandidateChunk]:
        """Generate dense embedding for query and execute vector search."""
        if not query.strip():
            return []

        limit = top_k if top_k is not None and top_k > 0 else self._default_top_k
        query_vector = await self._embedding_provider.embed_query(query)

        if hasattr(self._search_backend, "search_vector"):
            candidates = await self._search_backend.search_vector(
                owner_id=owner_id,
                query_embedding=query_vector,
                top_k=limit,
                filter=filter,
            )
        elif callable(self._search_backend):
            candidates = await self._search_backend(
                query_vector,
                owner_id,
                filter,
                limit,
            )
        else:
            raise TypeError(f"Unsupported vector search backend type: {type(self._search_backend)}")

        # Ensure retrieval_method tag is set to VECTOR
        for c in candidates:
            c.retrieval_method = RetrievalMethod.VECTOR

        return candidates
