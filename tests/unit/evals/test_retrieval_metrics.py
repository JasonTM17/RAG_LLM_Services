"""Unit tests for deterministic retrieval metrics."""

from evals.evaluators.retrieval_metrics import evaluate_retrieval_metrics
from evals.schema import EvaluationExample, RetrievedSource


def test_retrieval_metrics_reward_ranked_expected_sources() -> None:
    examples = [
        EvaluationExample(
            question="q1",
            expected_answer="a1",
            expected_sources=("[S1]", "[S3]"),
            metadata={},
            retrieved_sources=(
                RetrievedSource("[S1]", rank=1),
                RetrievedSource("[S2]", rank=2),
                RetrievedSource("[S3]", rank=3),
            ),
            answer="a1 [S1] [S3]",
        ),
        EvaluationExample(
            question="q2",
            expected_answer="a2",
            expected_sources=("[S4]",),
            metadata={},
            retrieved_sources=(RetrievedSource("[S9]", rank=1),),
            answer="a2 [S9]",
        ),
    ]

    metrics = evaluate_retrieval_metrics(examples, k=3)

    assert metrics.retrieval_hit_rate == 0.5
    assert metrics.recall_at_k == 0.5
    assert metrics.mrr == 0.5
    assert 0.45 < metrics.ndcg_at_k < 0.47
    assert metrics.context_relevance == 0.3333


def test_retrieval_metrics_handle_empty_dataset() -> None:
    metrics = evaluate_retrieval_metrics([], k=5)

    assert metrics.as_dict() == {
        "retrieval_hit_rate": 0.0,
        "recall_at_k": 0.0,
        "mrr": 0.0,
        "ndcg_at_k": 0.0,
        "context_relevance": 0.0,
    }
