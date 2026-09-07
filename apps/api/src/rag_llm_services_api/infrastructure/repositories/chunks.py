"""Repository for document chunks with transactional replacement and hybrid retrieval search."""

from __future__ import annotations

import math
import re
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from rag_llm_services_api.db.models.document import DocumentModel
from rag_llm_services_api.db.models.document_chunk import DocumentChunkModel
from rag_llm_services_api.domain.documents import DocumentStatus
from rag_llm_services_rag.retrieval.types import (
    CandidateChunk,
    RetrievalFilter,
    RetrievalMethod,
)

_TOKEN_RE = re.compile(r"\w+")


def _cosine_similarity(v1: list[float], v2: list[float]) -> float:
    """Compute cosine similarity between two float vectors."""
    dot = sum(a * b for a, b in zip(v1, v2, strict=False))
    norm_v1 = math.sqrt(sum(a * a for a in v1))
    norm_v2 = math.sqrt(sum(b * b for b in v2))
    if norm_v1 == 0.0 or norm_v2 == 0.0:
        return 0.0
    return dot / (norm_v1 * norm_v2)


def _metadata_int(metadata: dict[str, Any], *keys: str) -> int | None:
    for key in keys:
        value = metadata.get(key)
        if value is None:
            continue
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.isdecimal():
            return int(value)
    return None


def _metadata_str(metadata: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = metadata.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _matches_metadata_filter(metadata: dict[str, Any], filter: RetrievalFilter | None) -> bool:
    if filter is None:
        return True
    if filter.metadata and not all(metadata.get(k) == v for k, v in filter.metadata.items()):
        return False
    if filter.page is not None:
        page = _metadata_int(metadata, "page_number", "page")
        if page != filter.page:
            return False
    if filter.section is not None:
        section = _metadata_str(metadata, "section_header", "section")
        if section != filter.section:
            return False
    return True


def _apply_filter_clause(stmt: Any, filter: RetrievalFilter | None) -> Any:
    if filter is None:
        return stmt
    if filter.knowledge_base_id is not None:
        stmt = stmt.where(DocumentModel.knowledge_base_id == filter.knowledge_base_id)
    if filter.document_ids:
        stmt = stmt.where(DocumentChunkModel.document_id.in_(filter.document_ids))
    if filter.mime_types:
        stmt = stmt.where(DocumentModel.content_type.in_(filter.mime_types))
    if filter.page is not None:
        stmt = stmt.where(
            or_(
                DocumentChunkModel.metadata_json["page_number"].as_integer() == filter.page,
                DocumentChunkModel.metadata_json["page"].as_integer() == filter.page,
            )
        )
    if filter.section is not None:
        stmt = stmt.where(
            or_(
                DocumentChunkModel.metadata_json["section_header"].as_string() == filter.section,
                DocumentChunkModel.metadata_json["section"].as_string() == filter.section,
            )
        )
    if filter.created_after is not None:
        stmt = stmt.where(DocumentModel.created_at >= filter.created_after)
    if filter.created_before is not None:
        stmt = stmt.where(DocumentModel.created_at <= filter.created_before)
    if filter.metadata:
        stmt = stmt.where(DocumentChunkModel.metadata_json.contains(filter.metadata))
    return stmt


@dataclass(frozen=True)
class ChunkCreateData:
    """Input data for creating a document chunk."""

    chunk_index: int
    content: str
    token_count: int
    metadata_json: dict[str, Any]
    embedding: list[float] | None = None


class ChunkRepository:
    """Repository managing document chunk persistence and similarity/keyword retrieval."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def replace_document_chunks_transactionally(
        self,
        owner_id: UUID,
        document_id: UUID,
        document_version_id: UUID,
        chunks_data: list[ChunkCreateData],
    ) -> list[DocumentChunkModel]:
        """Atomically replace all chunks for a document version."""
        # 1. Delete existing chunks for this version
        delete_stmt = delete(DocumentChunkModel).where(
            DocumentChunkModel.owner_id == owner_id,
            DocumentChunkModel.document_id == document_id,
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

    def _is_postgres(self) -> bool:
        bind = self._session.bind
        if bind is not None:
            return bind.dialect.name == "postgresql"
        return True

    async def search_vector(
        self,
        owner_id: UUID,
        query_embedding: list[float],
        top_k: int = 10,
        filter: RetrievalFilter | None = None,
    ) -> list[CandidateChunk]:
        """Execute vector similarity search scoped to owner_id with optional metadata filters."""
        is_postgres = self._is_postgres()

        if is_postgres:
            # Native pgvector cosine distance: embedding <=> query_embedding
            distance_expr = DocumentChunkModel.embedding.cosine_distance(query_embedding).label(
                "distance"
            )
            stmt = (
                select(DocumentChunkModel, DocumentModel, distance_expr)
                .join(DocumentModel, DocumentChunkModel.document_id == DocumentModel.id)
                .where(
                    DocumentChunkModel.owner_id == owner_id,
                    DocumentModel.status == DocumentStatus.INDEXED.value,
                    DocumentChunkModel.document_version_id == DocumentModel.current_version_id,
                    DocumentChunkModel.embedding.is_not(None),
                )
            )

            stmt = _apply_filter_clause(stmt, filter)

            stmt = stmt.order_by(distance_expr.asc()).limit(top_k)
            rows = (await self._session.execute(stmt)).all()

            results: list[CandidateChunk] = []
            for chunk_row, doc_row, dist in rows:
                score = round(max(0.0, min(1.0, 1.0 - float(dist))), 6)
                meta = dict(chunk_row.metadata_json)
                results.append(
                    CandidateChunk(
                        chunk_id=chunk_row.id,
                        document_id=chunk_row.document_id,
                        document_version_id=chunk_row.document_version_id,
                        content=chunk_row.content,
                        score=score,
                        retrieval_method=RetrievalMethod.VECTOR,
                        chunk_index=chunk_row.chunk_index,
                        token_count=chunk_row.token_count,
                        filename=meta.get("filename") or doc_row.filename,
                        page=meta.get("page_number") or meta.get("page"),
                        section=meta.get("section_header") or meta.get("section"),
                        metadata=meta,
                    )
                )
            return results

        # SQLite/in-memory fallback for test hermeticity
        stmt_fallback = (
            select(DocumentChunkModel, DocumentModel)
            .join(DocumentModel, DocumentChunkModel.document_id == DocumentModel.id)
            .where(
                DocumentChunkModel.owner_id == owner_id,
                DocumentModel.status == DocumentStatus.INDEXED.value,
                DocumentChunkModel.document_version_id == DocumentModel.current_version_id,
                DocumentChunkModel.embedding.is_not(None),
            )
        )
        if filter:
            if filter.knowledge_base_id is not None:
                stmt_fallback = stmt_fallback.where(
                    DocumentModel.knowledge_base_id == filter.knowledge_base_id
                )
            if filter.document_ids:
                stmt_fallback = stmt_fallback.where(
                    DocumentChunkModel.document_id.in_(filter.document_ids)
                )
            if filter.mime_types:
                stmt_fallback = stmt_fallback.where(
                    DocumentModel.content_type.in_(filter.mime_types)
                )
            if filter.created_after is not None:
                stmt_fallback = stmt_fallback.where(
                    DocumentModel.created_at >= filter.created_after
                )
            if filter.created_before is not None:
                stmt_fallback = stmt_fallback.where(
                    DocumentModel.created_at <= filter.created_before
                )

        all_rows = (await self._session.execute(stmt_fallback)).all()

        scored: list[tuple[float, DocumentChunkModel, DocumentModel]] = []
        for chunk_row, doc_row in all_rows:
            if not _matches_metadata_filter(chunk_row.metadata_json, filter):
                continue
            if chunk_row.embedding is not None:
                sim = _cosine_similarity(query_embedding, chunk_row.embedding)
                scored.append((sim, chunk_row, doc_row))

        scored.sort(key=lambda item: (-item[0], str(item[1].id)))
        scored = scored[:top_k]

        results_fallback: list[CandidateChunk] = []
        for sim, chunk_row, doc_row in scored:
            meta = dict(chunk_row.metadata_json)
            results_fallback.append(
                CandidateChunk(
                    chunk_id=chunk_row.id,
                    document_id=chunk_row.document_id,
                    document_version_id=chunk_row.document_version_id,
                    content=chunk_row.content,
                    score=round(sim, 6),
                    retrieval_method=RetrievalMethod.VECTOR,
                    chunk_index=chunk_row.chunk_index,
                    token_count=chunk_row.token_count,
                    filename=meta.get("filename") or doc_row.filename,
                    page=meta.get("page_number") or meta.get("page"),
                    section=meta.get("section_header") or meta.get("section"),
                    metadata=meta,
                )
            )
        return results_fallback

    async def search_keyword(
        self,
        owner_id: UUID,
        query: str,
        top_k: int = 10,
        filter: RetrievalFilter | None = None,
    ) -> list[CandidateChunk]:
        """Execute full-text keyword search scoped to owner_id with optional metadata filters."""
        is_postgres = self._is_postgres()

        if is_postgres:
            tsv = func.to_tsvector("english", DocumentChunkModel.content)
            tsq = func.websearch_to_tsquery("english", query)
            rank_expr = func.ts_rank_cd(tsv, tsq).label("rank")

            stmt = (
                select(DocumentChunkModel, DocumentModel, rank_expr)
                .join(DocumentModel, DocumentChunkModel.document_id == DocumentModel.id)
                .where(
                    DocumentChunkModel.owner_id == owner_id,
                    DocumentModel.status == DocumentStatus.INDEXED.value,
                    DocumentChunkModel.document_version_id == DocumentModel.current_version_id,
                    tsv.op("@@")(tsq),
                )
            )

            stmt = _apply_filter_clause(stmt, filter)

            stmt = stmt.order_by(rank_expr.desc()).limit(top_k)
            rows = (await self._session.execute(stmt)).all()

            results: list[CandidateChunk] = []
            for chunk_row, doc_row, rk in rows:
                score = round(float(rk), 6)
                meta = dict(chunk_row.metadata_json)
                results.append(
                    CandidateChunk(
                        chunk_id=chunk_row.id,
                        document_id=chunk_row.document_id,
                        document_version_id=chunk_row.document_version_id,
                        content=chunk_row.content,
                        score=score,
                        retrieval_method=RetrievalMethod.KEYWORD,
                        chunk_index=chunk_row.chunk_index,
                        token_count=chunk_row.token_count,
                        filename=meta.get("filename") or doc_row.filename,
                        page=meta.get("page_number") or meta.get("page"),
                        section=meta.get("section_header") or meta.get("section"),
                        metadata=meta,
                    )
                )
            return results

        # SQLite/in-memory fallback for test hermeticity
        query_words = [w.lower() for w in _TOKEN_RE.findall(query)]
        if not query_words:
            return []

        stmt_fallback = (
            select(DocumentChunkModel, DocumentModel)
            .join(DocumentModel, DocumentChunkModel.document_id == DocumentModel.id)
            .where(
                DocumentChunkModel.owner_id == owner_id,
                DocumentModel.status == DocumentStatus.INDEXED.value,
                DocumentChunkModel.document_version_id == DocumentModel.current_version_id,
            )
        )
        if filter:
            if filter.knowledge_base_id is not None:
                stmt_fallback = stmt_fallback.where(
                    DocumentModel.knowledge_base_id == filter.knowledge_base_id
                )
            if filter.document_ids:
                stmt_fallback = stmt_fallback.where(
                    DocumentChunkModel.document_id.in_(filter.document_ids)
                )
            if filter.mime_types:
                stmt_fallback = stmt_fallback.where(
                    DocumentModel.content_type.in_(filter.mime_types)
                )
            if filter.created_after is not None:
                stmt_fallback = stmt_fallback.where(
                    DocumentModel.created_at >= filter.created_after
                )
            if filter.created_before is not None:
                stmt_fallback = stmt_fallback.where(
                    DocumentModel.created_at <= filter.created_before
                )

        all_rows = (await self._session.execute(stmt_fallback)).all()

        scored: list[tuple[float, DocumentChunkModel, DocumentModel]] = []
        for chunk_row, doc_row in all_rows:
            if not _matches_metadata_filter(chunk_row.metadata_json, filter):
                continue

            content_lower = chunk_row.content.lower()
            match_count = sum(content_lower.count(w) for w in query_words)
            if match_count > 0:
                score = round(match_count / (len(query_words) + 1.0), 6)
                scored.append((score, chunk_row, doc_row))

        scored.sort(key=lambda item: (-item[0], str(item[1].id)))
        scored = scored[:top_k]

        results_fallback: list[CandidateChunk] = []
        for score, chunk_row, doc_row in scored:
            meta = dict(chunk_row.metadata_json)
            results_fallback.append(
                CandidateChunk(
                    chunk_id=chunk_row.id,
                    document_id=chunk_row.document_id,
                    document_version_id=chunk_row.document_version_id,
                    content=chunk_row.content,
                    score=score,
                    retrieval_method=RetrievalMethod.KEYWORD,
                    chunk_index=chunk_row.chunk_index,
                    token_count=chunk_row.token_count,
                    filename=meta.get("filename") or doc_row.filename,
                    page=meta.get("page_number") or meta.get("page"),
                    section=meta.get("section_header") or meta.get("section"),
                    metadata=meta,
                )
            )
        return results_fallback
