"""Unit tests for citation correctness metrics."""

from evals.evaluators.citation_metrics import evaluate_citation_metrics
from evals.schema import EvaluationExample, RetrievedSource


def test_citation_correctness_fails_for_unavailable_source_id() -> None:
    example = EvaluationExample(
        question="q",
        expected_answer="a",
        expected_sources=("[S1]",),
        metadata={},
        retrieved_sources=(RetrievedSource("[S1]", rank=1),),
        answer="Answer cites a missing source. [S9]",
    )

    metrics = evaluate_citation_metrics([example])

    assert metrics.citation_correctness == 0.0
    assert metrics.missing_citation_count == 1
    assert metrics.examples[0].missing_source_ids == ("[S9]",)


def test_citation_metrics_track_expected_source_recall_and_precision() -> None:
    example = EvaluationExample(
        question="q",
        expected_answer="a",
        expected_sources=("[S1]", "[S2]"),
        metadata={},
        retrieved_sources=(RetrievedSource("[S1]", rank=1), RetrievedSource("[S2]", rank=2)),
        answer="Only one expected source is cited. [S1]",
    )

    metrics = evaluate_citation_metrics([example])

    assert metrics.citation_correctness == 1.0
    assert metrics.citation_recall == 0.5
    assert metrics.citation_precision == 1.0
    assert metrics.examples[0].uncited_expected_sources == ("[S2]",)
