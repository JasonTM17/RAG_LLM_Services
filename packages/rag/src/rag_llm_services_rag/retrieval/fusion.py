"""Reciprocal Rank Fusion (RRF) for combining vector and lexical search rankings."""

from __future__ import annotations

from uuid import UUID

from rag_llm_services_rag.retrieval.types import (
    CandidateChunk,
    RetrievalMethod,
    RetrievalResult,
)


class ReciprocalRankFusion:
    """Combines multiple ranked candidate lists using standard Reciprocal Rank Fusion.

    Formula:
        RRF_score = sum( w_m / (k + rank_m) ) for each retrieval list m

    Provides:
    - Configurable smoothing constant `k` (standard default k=60).
    - Configurable weights for vector and keyword ranking channels.
    - Deterministic tie-breaking by chunk ID for consistent ordering.
    - Method attribution: chunks appearing in both lists are tagged `RetrievalMethod.HYBRID`.
    """

    def __init__(
        self,
        k: int = 60,
        vector_weight: float = 1.0,
        keyword_weight: float = 1.0,
    ) -> None:
        if k <= 0:
            raise ValueError(f"RRF smoothing constant k must be positive, got {k}")
        self.k = k
        self.vector_weight = vector_weight
        self.keyword_weight = keyword_weight

    def fuse(
        self,
        vector_candidates: list[CandidateChunk],
        keyword_candidates: list[CandidateChunk],
        top_k: int | None = None,
    ) -> list[RetrievalResult]:
        """Fuse vector and keyword candidate lists into a single ranked result list."""
        ranked_channels: list[tuple[RetrievalMethod, list[CandidateChunk], float]] = [
            (RetrievalMethod.VECTOR, vector_candidates, self.vector_weight),
            (RetrievalMethod.KEYWORD, keyword_candidates, self.keyword_weight),
        ]
        return self.fuse_ranked_lists(ranked_channels, top_k=top_k)

    def fuse_ranked_lists(
        self,
        channels: list[tuple[RetrievalMethod, list[CandidateChunk], float]],
        top_k: int | None = None,
    ) -> list[RetrievalResult]:
        """Fuse an arbitrary set of ranked candidate lists with channel weights.

        Each tuple contains (channel_method, candidates, weight).
        """
        scores: dict[UUID, float] = {}
        seen_methods: dict[UUID, set[RetrievalMethod]] = {}
        candidate_data: dict[UUID, CandidateChunk] = {}

        for method, candidate_list, weight in channels:
            for rank_idx, candidate in enumerate(candidate_list, start=1):
                chunk_id = candidate.chunk_id
                rrf_contrib = weight / (self.k + rank_idx)

                scores[chunk_id] = scores.get(chunk_id, 0.0) + rrf_contrib

                if chunk_id not in seen_methods:
                    seen_methods[chunk_id] = set()
                seen_methods[chunk_id].add(method)

                if chunk_id not in candidate_data:
                    candidate_data[chunk_id] = candidate

        if not scores:
            return []

        # Deterministic sorting: highest score first, tie-break by chunk_id string representation
        sorted_chunk_ids = sorted(
            scores.keys(),
            key=lambda cid: (-scores[cid], str(cid)),
        )

        if top_k is not None and top_k > 0:
            sorted_chunk_ids = sorted_chunk_ids[:top_k]

        results: list[RetrievalResult] = []
        for rank, chunk_id in enumerate(sorted_chunk_ids, start=1):
            source_candidate = candidate_data[chunk_id]
            methods = seen_methods[chunk_id]

            if len(methods) > 1 or RetrievalMethod.HYBRID in methods:
                effective_method = RetrievalMethod.HYBRID
            elif RetrievalMethod.VECTOR in methods:
                effective_method = RetrievalMethod.VECTOR
            else:
                effective_method = RetrievalMethod.KEYWORD

            result = RetrievalResult(
                chunk_id=source_candidate.chunk_id,
                document_id=source_candidate.document_id,
                content=source_candidate.content,
                score=round(scores[chunk_id], 8),
                retrieval_method=effective_method,
                filename=source_candidate.filename,
                page=source_candidate.page,
                section=source_candidate.section,
                chunk_index=source_candidate.chunk_index,
                token_count=source_candidate.token_count,
                rank=rank,
                metadata=dict(source_candidate.metadata),
            )
            results.append(result)

        return results
