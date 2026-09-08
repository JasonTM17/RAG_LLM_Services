"""Deterministic retrieval ranking metrics for fixture-safe RAG evaluation."""

from __future__ import annotations

import math
from dataclasses import dataclass

from evals.schema import EvaluationExample


@dataclass(frozen=True)
class RetrievalMetrics:
    """Aggregate retrieval metric values."""

    retrieval_hit_rate: float
    recall_at_k: float
    mrr: float
    ndcg_at_k: float
    context_relevance: float

    def as_dict(self) -> dict[str, float]:
        """Return a JSON-serializable metric map."""
        return {
            "retrieval_hit_rate": self.retrieval_hit_rate,
            "recall_at_k": self.recall_at_k,
            "mrr": self.mrr,
            "ndcg_at_k": self.ndcg_at_k,
            "context_relevance": self.context_relevance,
        }


def evaluate_retrieval_metrics(
    examples: list[EvaluationExample],
    *,
    k: int,
) -> RetrievalMetrics:
    """Compute hit rate, Recall@K, MRR, nDCG@K, and context relevance."""
    if not examples:
        return RetrievalMetrics(0.0, 0.0, 0.0, 0.0, 0.0)
    hit_scores: list[float] = []
    recall_scores: list[float] = []
    reciprocal_ranks: list[float] = []
    ndcg_scores: list[float] = []
    relevance_scores: list[float] = []
    for example in examples:
        expected = set(example.expected_sources)
        retrieved = example.top_retrieved_source_ids(k)
        retrieved_set = set(retrieved)
        relevant_count = len(expected & retrieved_set)

        hit_scores.append(1.0 if relevant_count else 0.0)
        recall_scores.append(relevant_count / len(expected) if expected else 1.0)
        reciprocal_ranks.append(_reciprocal_rank(retrieved, expected))
        ndcg_scores.append(_ndcg(retrieved, expected, k))
        denominator = min(k, len(retrieved)) or 1
        relevance_scores.append(relevant_count / denominator)

    return RetrievalMetrics(
        retrieval_hit_rate=_mean(hit_scores),
        recall_at_k=_mean(recall_scores),
        mrr=_mean(reciprocal_ranks),
        ndcg_at_k=_mean(ndcg_scores),
        context_relevance=_mean(relevance_scores),
    )


def _reciprocal_rank(retrieved: tuple[str, ...], expected: set[str]) -> float:
    for rank, source_id in enumerate(retrieved, start=1):
        if source_id in expected:
            return 1.0 / rank
    return 0.0


def _ndcg(retrieved: tuple[str, ...], expected: set[str], k: int) -> float:
    dcg = 0.0
    for rank, source_id in enumerate(retrieved[:k], start=1):
        if source_id in expected:
            dcg += 1.0 / math.log2(rank + 1)
    ideal_relevant = min(len(expected), k)
    if ideal_relevant == 0:
        return 1.0
    ideal_dcg = sum(1.0 / math.log2(rank + 1) for rank in range(1, ideal_relevant + 1))
    return dcg / ideal_dcg


def _mean(values: list[float]) -> float:
    if not values:
        return 0.0
    return round(sum(values) / len(values), 4)
