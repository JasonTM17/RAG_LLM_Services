"""Unit tests for deterministic answer relevance and faithfulness metrics."""

from evals.evaluators.answer_metrics import evaluate_answer_metrics
from evals.schema import EvaluationExample, RetrievedSource


def test_answer_metrics_score_fixture_grounding() -> None:
    example = EvaluationExample(
        question="q",
        expected_answer="Hybrid retrieval combines vector search and keyword search.",
        expected_sources=("[S1]",),
        metadata={},
        retrieved_sources=(
            RetrievedSource(
                "[S1]",
                rank=1,
                content="Hybrid retrieval combines vector search and keyword search.",
            ),
        ),
        answer="Hybrid retrieval combines vector search and keyword search. [S1]",
    )

    metrics = evaluate_answer_metrics([example])

    assert metrics.answer_relevance == 1.0
    assert metrics.faithfulness == 1.0


def test_answer_metrics_penalize_ungrounded_answer() -> None:
    example = EvaluationExample(
        question="q",
        expected_answer="Use fixture evaluation.",
        expected_sources=("[S1]",),
        metadata={},
        retrieved_sources=(RetrievedSource("[S1]", rank=1, content="Use fixture evaluation."),),
        answer="The answer discusses unrelated production deployment. [S1]",
    )

    metrics = evaluate_answer_metrics([example])

    assert metrics.answer_relevance < 0.5
    assert metrics.faithfulness < 0.5
