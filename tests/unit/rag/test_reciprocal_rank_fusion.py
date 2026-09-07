"""Unit tests for Reciprocal Rank Fusion (RRF) algorithm."""

from __future__ import annotations

import uuid

import pytest

from rag_llm_services_rag.retrieval.fusion import ReciprocalRankFusion
from rag_llm_services_rag.retrieval.types import (
    CandidateChunk,
    RetrievalMethod,
)


def _make_candidate(
    chunk_id: uuid.UUID | None = None,
    document_id: uuid.UUID | None = None,
    content: str = "test content",
    score: float = 0.9,
    method: RetrievalMethod = RetrievalMethod.VECTOR,
    filename: str = "test.txt",
    page: int | None = None,
    section: str | None = None,
) -> CandidateChunk:
    return CandidateChunk(
        chunk_id=chunk_id or uuid.uuid4(),
        document_id=document_id or uuid.uuid4(),
        content=content,
        score=score,
        retrieval_method=method,
        filename=filename,
        page=page,
        section=section,
    )


def test_rrf_both_channels_boost_score() -> None:
    """A chunk appearing in both vector and keyword channels receives an RRF score boost."""
    chunk_shared = uuid.uuid4()
    chunk_vec_only = uuid.uuid4()
    chunk_kw_only = uuid.uuid4()

    c_shared_v = _make_candidate(chunk_id=chunk_shared, content="Shared chunk", score=0.95)
    c_vec_only = _make_candidate(chunk_id=chunk_vec_only, content="Vector only", score=0.90)

    c_kw_only = _make_candidate(
        chunk_id=chunk_kw_only, content="Keyword only", score=0.85, method=RetrievalMethod.KEYWORD
    )
    c_shared_k = _make_candidate(
        chunk_id=chunk_shared, content="Shared chunk", score=0.80, method=RetrievalMethod.KEYWORD
    )

    vector_candidates = [c_shared_v, c_vec_only]  # shared rank 1, vec_only rank 2
    keyword_candidates = [c_shared_k, c_kw_only]  # shared rank 1, kw_only rank 2

    fusion = ReciprocalRankFusion(k=60)
    results = fusion.fuse(vector_candidates, keyword_candidates)

    assert len(results) == 3
    # Shared item should rank #1 because it received score from both channels
    assert results[0].chunk_id == chunk_shared
    assert results[0].retrieval_method == RetrievalMethod.HYBRID
    assert results[0].rank == 1

    # Exact RRF calculation check: 1/(60+1) + 1/(60+1) = 2/61 ≈ 0.03278689
    expected_score = round(1.0 / 61.0 + 1.0 / 61.0, 8)
    assert abs(results[0].score - expected_score) < 1e-6


def test_rrf_configurable_k() -> None:
    """RRF score adjusts according to configured smoothing constant k."""
    chunk_a = uuid.uuid4()
    c_a = _make_candidate(chunk_id=chunk_a)

    fusion_k60 = ReciprocalRankFusion(k=60)
    res_k60 = fusion_k60.fuse([c_a], [])
    assert res_k60[0].score == round(1.0 / 61.0, 8)

    fusion_k10 = ReciprocalRankFusion(k=10)
    res_k10 = fusion_k10.fuse([c_a], [])
    assert res_k10[0].score == round(1.0 / 11.0, 8)


def test_rrf_negative_k_raises() -> None:
    with pytest.raises(ValueError, match="must be positive"):
        ReciprocalRankFusion(k=0)


def test_rrf_channel_weights() -> None:
    """Configuring channel weights weights vector and keyword contributions."""
    chunk_v = uuid.uuid4()
    chunk_k = uuid.uuid4()

    c_v = _make_candidate(chunk_id=chunk_v, score=0.9, method=RetrievalMethod.VECTOR)
    c_k = _make_candidate(chunk_id=chunk_k, score=0.9, method=RetrievalMethod.KEYWORD)

    # Vector weight 2.0, Keyword weight 0.5
    fusion = ReciprocalRankFusion(k=60, vector_weight=2.0, keyword_weight=0.5)
    results = fusion.fuse([c_v], [c_k])

    assert results[0].chunk_id == chunk_v
    assert results[0].score == round(2.0 / 61.0, 8)
    assert results[1].chunk_id == chunk_k
    assert results[1].score == round(0.5 / 61.0, 8)


def test_rrf_deterministic_tie_breaking() -> None:
    """When two candidates have the exact same RRF score, order is deterministically sorted by chunk ID."""
    id_1 = uuid.UUID("00000000-0000-0000-0000-000000000001")
    id_2 = uuid.UUID("00000000-0000-0000-0000-000000000002")

    c1 = _make_candidate(chunk_id=id_1, content="C1")
    c2 = _make_candidate(chunk_id=id_2, content="C2")

    # In vector only, rank 1 vs rank 2 gives different scores
    # But if c1 is rank 1 in vector and c2 is rank 1 in keyword with equal weights:
    fusion = ReciprocalRankFusion(k=60, vector_weight=1.0, keyword_weight=1.0)
    results = fusion.fuse([c1], [c2])

    # Both have score 1/61
    assert results[0].score == results[1].score
    # Tie-break by chunk ID string: id_1 comes before id_2
    assert results[0].chunk_id == id_1
    assert results[1].chunk_id == id_2


def test_rrf_top_k_bounding() -> None:
    """Requesting top_k limits the fused result length."""
    candidates = [_make_candidate() for _ in range(10)]
    fusion = ReciprocalRankFusion(k=60)
    results = fusion.fuse(candidates, [], top_k=3)
    assert len(results) == 3
    assert results[0].rank == 1
    assert results[1].rank == 2
    assert results[2].rank == 3


def test_rrf_empty_inputs() -> None:
    fusion = ReciprocalRankFusion(k=60)
    assert fusion.fuse([], []) == []

    single = [_make_candidate()]
    assert len(fusion.fuse(single, [])) == 1
    assert len(fusion.fuse([], single)) == 1
