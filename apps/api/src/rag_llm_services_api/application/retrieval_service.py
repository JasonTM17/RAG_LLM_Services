"""Retrieval application service orchestrating query normalization, hybrid search, RRF fusion, reranking, and context selection."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from rag_llm_services_api.infrastructure.repositories.chunks import ChunkRepository
from rag_llm_services_api.infrastructure.repositories.rag_queries import RagQueryRepository
from rag_llm_services_embeddings.base import EmbeddingProvider
from rag_llm_services_observability.metrics import (
    record_cache_miss,
    record_error,
    record_retrieval_query,
    record_retrieval_stage_latency,
    record_retrieved_chunks,
)
from rag_llm_services_rag.retrieval.context import ContextBuilder
from rag_llm_services_rag.retrieval.fusion import ReciprocalRankFusion
from rag_llm_services_rag.retrieval.keyword import KeywordRetriever
from rag_llm_services_rag.retrieval.query import QueryNormalizer
from rag_llm_services_rag.retrieval.reranker import RerankerProvider
from rag_llm_services_rag.retrieval.types import (
    CandidateChunk,
    ContextBundle,
    RetrievalFilter,
    RetrievalMethod,
    RetrievalResult,
)
from rag_llm_services_rag.retrieval.vector import VectorRetriever

logger = logging.getLogger(__name__)


@dataclass
class RetrievalServiceResponse:
    """Orchestrated retrieval search output."""

    query: str
    retrieval_method: RetrievalMethod
    results: list[RetrievalResult]
    context_bundle: ContextBundle | None
    latency_ms: float
    stage_latencies_ms: dict[str, float]
    total_results: int


class RetrievalService:
    """Orchestrator for the end-to-end hybrid retrieval pipeline."""

    def __init__(
        self,
        chunk_repo: ChunkRepository,
        rag_query_repo: RagQueryRepository,
        embedding_provider: EmbeddingProvider,
        reranker_provider: RerankerProvider,
        normalizer: QueryNormalizer | None = None,
        fusion: ReciprocalRankFusion | None = None,
        context_builder: ContextBuilder | None = None,
        vector_retriever: VectorRetriever | None = None,
        keyword_retriever: KeywordRetriever | None = None,
        default_context_budget: int = 6000,
        default_vector_top_k: int = 10,
        default_keyword_top_k: int = 10,
        default_rerank_top_k: int = 8,
    ) -> None:
        self._chunk_repo = chunk_repo
        self._rag_query_repo = rag_query_repo
        self._embedding_provider = embedding_provider
        self._reranker_provider = reranker_provider
        self._normalizer = normalizer or QueryNormalizer()
        self._fusion = fusion or ReciprocalRankFusion()
        self._context_builder = context_builder or ContextBuilder(
            default_max_budget=default_context_budget
        )
        self._default_context_budget = default_context_budget
        self._default_vector_top_k = default_vector_top_k
        self._default_keyword_top_k = default_keyword_top_k
        self._default_rerank_top_k = default_rerank_top_k

        self._vector_retriever = vector_retriever or VectorRetriever(
            embedding_provider=self._embedding_provider,
            search_backend=self._chunk_repo,
            default_top_k=default_vector_top_k,
        )
        self._keyword_retriever = keyword_retriever or KeywordRetriever(
            search_backend=self._chunk_repo,
            normalizer=self._normalizer,
            default_top_k=default_keyword_top_k,
        )

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
    ) -> RetrievalServiceResponse:
        """Execute end-to-end retrieval search with tenant isolation."""
        start_time = time.perf_counter()
        # Phase 08 ships retrieval cache key conventions; until read-through
        # caching is implemented, searches are observed as retrieval cache misses.
        record_cache_miss("retrieval")
        stage_latencies_ms = {
            "normalize": 0.0,
            "vector": 0.0,
            "keyword": 0.0,
            "fusion": 0.0,
            "rerank": 0.0,
            "context": 0.0,
        }

        def finish_stage(stage: str, stage_start: float) -> None:
            latency_ms = round((time.perf_counter() - stage_start) * 1000.0, 2)
            stage_latencies_ms[stage] = latency_ms
            record_retrieval_stage_latency(stage, latency_ms)

        effective_vector_top_k = vector_top_k or self._default_vector_top_k
        effective_keyword_top_k = keyword_top_k or self._default_keyword_top_k
        effective_rerank_top_k = rerank_top_k or self._default_rerank_top_k

        # 1. Normalize query
        stage_start = time.perf_counter()
        normalized_query = self._normalizer.normalize(query)
        finish_stage("normalize", stage_start)
        if not normalized_query:
            elapsed_ms = round((time.perf_counter() - start_time) * 1000.0, 2)
            record_retrieval_stage_latency("total", elapsed_ms)
            method_label = method.value if isinstance(method, RetrievalMethod) else str(method)
            record_retrieval_query(method_label)
            record_retrieved_chunks(method_label, 0)
            return RetrievalServiceResponse(
                query=query,
                retrieval_method=method,
                results=[],
                context_bundle=ContextBundle(
                    context_text="",
                    cited_chunks=[],
                    total_tokens=0,
                    total_chunks=0,
                    max_budget=context_token_budget or self._default_context_budget,
                )
                if include_context_bundle
                else None,
                latency_ms=elapsed_ms,
                stage_latencies_ms=stage_latencies_ms,
                total_results=0,
            )

        # 2. Vector search channel
        vector_candidates: list[CandidateChunk] = []
        if method in (RetrievalMethod.VECTOR, RetrievalMethod.HYBRID):
            stage_start = time.perf_counter()
            vector_candidates = await self._vector_retriever.retrieve(
                query=normalized_query,
                owner_id=owner_id,
                filter=filter,
                top_k=effective_vector_top_k,
            )
            finish_stage("vector", stage_start)

        # 3. Keyword search channel
        keyword_candidates: list[CandidateChunk] = []
        if method in (RetrievalMethod.KEYWORD, RetrievalMethod.HYBRID):
            stage_start = time.perf_counter()
            keyword_candidates = await self._keyword_retriever.retrieve(
                query=normalized_query,
                owner_id=owner_id,
                filter=filter,
                top_k=effective_keyword_top_k,
            )
            finish_stage("keyword", stage_start)

        # 4. Rank fusion
        stage_start = time.perf_counter()
        candidates: list[RetrievalResult] = []
        if method == RetrievalMethod.HYBRID:
            fusion_top_k = max(effective_vector_top_k, effective_keyword_top_k)
            candidates = self._fusion.fuse(
                vector_candidates=vector_candidates,
                keyword_candidates=keyword_candidates,
                top_k=fusion_top_k,
            )
        elif method == RetrievalMethod.VECTOR:
            candidates = [
                RetrievalResult(
                    chunk_id=c.chunk_id,
                    document_id=c.document_id,
                    content=c.content,
                    score=c.score,
                    retrieval_method=RetrievalMethod.VECTOR,
                    filename=c.filename,
                    page=c.page,
                    section=c.section,
                    chunk_index=c.chunk_index,
                    token_count=c.token_count,
                    rank=idx,
                    metadata=dict(c.metadata),
                )
                for idx, c in enumerate(vector_candidates[:effective_vector_top_k], start=1)
            ]
        else:  # KEYWORD
            candidates = [
                RetrievalResult(
                    chunk_id=c.chunk_id,
                    document_id=c.document_id,
                    content=c.content,
                    score=c.score,
                    retrieval_method=RetrievalMethod.KEYWORD,
                    filename=c.filename,
                    page=c.page,
                    section=c.section,
                    chunk_index=c.chunk_index,
                    token_count=c.token_count,
                    rank=idx,
                    metadata=dict(c.metadata),
                )
                for idx, c in enumerate(keyword_candidates[:effective_keyword_top_k], start=1)
            ]
        finish_stage("fusion", stage_start)

        # 5. Reranking
        stage_start = time.perf_counter()
        reranked_results = await self._reranker_provider.rerank(
            query=normalized_query,
            candidates=candidates,
            top_k=effective_rerank_top_k,
        )
        finish_stage("rerank", stage_start)

        # 6. Context selection
        context_bundle: ContextBundle | None = None
        if include_context_bundle:
            stage_start = time.perf_counter()
            budget = context_token_budget or self._default_context_budget
            context_bundle = self._context_builder.build(reranked_results, max_budget=budget)
            finish_stage("context", stage_start)

        elapsed_ms = (time.perf_counter() - start_time) * 1000.0
        rounded_elapsed_ms = round(elapsed_ms, 2)
        record_retrieval_stage_latency("total", rounded_elapsed_ms)
        method_label = method.value if isinstance(method, RetrievalMethod) else str(method)
        record_retrieval_query(method_label)
        record_retrieved_chunks(method_label, len(reranked_results))

        # 7. Record query audit event (avoid logging sensitive query/PII in log labels)
        filter_dict: dict[str, Any] = {}
        if filter:
            if filter.knowledge_base_id:
                filter_dict["knowledge_base_id"] = str(filter.knowledge_base_id)
            if filter.document_ids:
                filter_dict["document_ids"] = [str(did) for did in filter.document_ids]
            if filter.mime_types:
                filter_dict["mime_types"] = filter.mime_types
            if filter.page is not None:
                filter_dict["page"] = filter.page
            if filter.section is not None:
                filter_dict["section"] = filter.section
            if filter.created_after is not None:
                filter_dict["created_after"] = filter.created_after.isoformat()
            if filter.created_before is not None:
                filter_dict["created_before"] = filter.created_before.isoformat()
            if filter.metadata:
                filter_dict["metadata"] = filter.metadata

        try:
            await self._rag_query_repo.record_query(
                owner_id=owner_id,
                query_text=normalized_query,
                retrieval_method=method.value
                if isinstance(method, RetrievalMethod)
                else str(method),
                result_count=len(reranked_results),
                latency_ms=elapsed_ms,
                result_chunk_ids=[c.chunk_id for c in reranked_results],
                knowledge_base_id=filter.knowledge_base_id if filter else None,
                vector_top_k=effective_vector_top_k,
                keyword_top_k=effective_keyword_top_k,
                rerank_top_k=effective_rerank_top_k,
                filter_json=filter_dict,
                stage_latencies_ms=stage_latencies_ms,
            )
        except Exception:
            # Audit logging failure must not block the search response
            record_error("retrieval", "exception")
            logger.warning(
                "Failed to record retrieval audit query event",
                exc_info=True,
                extra={
                    "stage": "retrieval.audit",
                    "dependency": "database",
                    "status": "failed",
                    "error_code": "RETRIEVAL_AUDIT_FAILED",
                },
            )

        logger.info(
            "Retrieval search completed in %.2f ms (results=%d, method=%s)",
            elapsed_ms,
            len(reranked_results),
            method_label,
            extra={
                "stage": "retrieval.total",
                "dependency": "rag",
                "status": "succeeded",
                "latency_ms": rounded_elapsed_ms,
                "method": method_label,
                "result_count": len(reranked_results),
            },
        )

        return RetrievalServiceResponse(
            query=normalized_query,
            retrieval_method=method,
            results=reranked_results,
            context_bundle=context_bundle,
            latency_ms=rounded_elapsed_ms,
            stage_latencies_ms=stage_latencies_ms,
            total_results=len(reranked_results),
        )
