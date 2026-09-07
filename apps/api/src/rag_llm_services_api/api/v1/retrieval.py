"""API router for RAG retrieval and search endpoints."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from rag_llm_services_api.api.dependencies.auth import get_current_user_id
from rag_llm_services_api.api.v1.schemas.retrieval import (
    CitedChunkResponse,
    ContextBundleResponse,
    RetrievalChunkResponse,
    RetrievalSearchRequest,
    RetrievalSearchResponse,
)
from rag_llm_services_api.application.retrieval_service import RetrievalService
from rag_llm_services_api.core.config import Settings, get_settings
from rag_llm_services_api.db.session import get_session
from rag_llm_services_api.infrastructure.embeddings import get_embedding_provider
from rag_llm_services_api.infrastructure.repositories.chunks import ChunkRepository
from rag_llm_services_api.infrastructure.repositories.rag_queries import RagQueryRepository
from rag_llm_services_api.infrastructure.reranker import get_reranker_provider
from rag_llm_services_rag.retrieval.fusion import ReciprocalRankFusion

router = APIRouter(prefix="/retrieval", tags=["retrieval"])


def get_retrieval_service(
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> RetrievalService:
    """Dependency assembling the RetrievalService."""
    chunk_repo = ChunkRepository(session)
    rag_query_repo = RagQueryRepository(session)
    embedding_provider = get_embedding_provider(settings)
    reranker_provider = get_reranker_provider(settings)
    return RetrievalService(
        chunk_repo=chunk_repo,
        rag_query_repo=rag_query_repo,
        embedding_provider=embedding_provider,
        reranker_provider=reranker_provider,
        fusion=ReciprocalRankFusion(
            k=settings.rag.rrf_k,
            vector_weight=settings.rag.rrf_vector_weight,
            keyword_weight=settings.rag.rrf_keyword_weight,
        ),
        default_context_budget=settings.rag.context_token_budget,
        default_vector_top_k=settings.rag.vector_top_k,
        default_keyword_top_k=settings.rag.keyword_top_k,
        default_rerank_top_k=settings.rag.rerank_top_k,
    )


@router.post("/search", response_model=RetrievalSearchResponse)
async def search(
    payload: RetrievalSearchRequest,
    user_id: Annotated[UUID, Depends(get_current_user_id)],
    service: Annotated[RetrievalService, Depends(get_retrieval_service)],
) -> RetrievalSearchResponse:
    """Execute hybrid, vector, or keyword search and return source-labeled context."""
    domain_filter = payload.filter.to_domain() if payload.filter else None

    response = await service.search(
        owner_id=user_id,
        query=payload.query,
        method=payload.method,
        filter=domain_filter,
        vector_top_k=payload.vector_top_k,
        keyword_top_k=payload.keyword_top_k,
        rerank_top_k=payload.rerank_top_k,
        context_token_budget=payload.context_token_budget,
        include_context_bundle=payload.include_context_bundle,
    )

    chunk_responses = [
        RetrievalChunkResponse(
            chunk_id=c.chunk_id,
            document_id=c.document_id,
            content=c.content,
            score=c.score,
            retrieval_method=c.retrieval_method,
            filename=c.filename,
            page=c.page,
            section=c.section,
            chunk_index=c.chunk_index,
            token_count=c.token_count,
            rank=c.rank,
            metadata=c.metadata,
        )
        for c in response.results
    ]

    bundle_response: ContextBundleResponse | None = None
    if response.context_bundle:
        cited_responses = [
            CitedChunkResponse(
                source_id=chunk.source_id,
                chunk_id=chunk.chunk_id,
                document_id=chunk.document_id,
                content=chunk.content,
                filename=chunk.filename,
                page=chunk.page,
                section=chunk.section,
                token_count=chunk.token_count,
                score=chunk.score,
                retrieval_method=chunk.retrieval_method,
                metadata=chunk.metadata,
            )
            for chunk in response.context_bundle.cited_chunks
        ]
        bundle_response = ContextBundleResponse(
            context_text=response.context_bundle.context_text,
            cited_chunks=cited_responses,
            total_tokens=response.context_bundle.total_tokens,
            total_chunks=response.context_bundle.total_chunks,
            max_budget=response.context_bundle.max_budget,
        )

    return RetrievalSearchResponse(
        query=response.query,
        retrieval_method=response.retrieval_method,
        results=chunk_responses,
        context_bundle=bundle_response,
        latency_ms=response.latency_ms,
        stage_latencies_ms=response.stage_latencies_ms,
        total_results=response.total_results,
    )
