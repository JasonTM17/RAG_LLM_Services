"""Citation correctness metrics for RAG answers."""

from __future__ import annotations

from dataclasses import dataclass

from evals.schema import EvaluationExample
from rag_llm_services_agents.citations import CitationValidationError, CitationValidator


@dataclass(frozen=True)
class CitationExampleResult:
    """Per-example citation validation details."""

    cited_source_ids: tuple[str, ...]
    missing_source_ids: tuple[str, ...]
    uncited_expected_sources: tuple[str, ...]


@dataclass(frozen=True)
class CitationMetrics:
    """Aggregate citation metric values."""

    citation_correctness: float
    citation_recall: float
    citation_precision: float
    missing_citation_count: int
    examples: tuple[CitationExampleResult, ...]

    def as_dict(self) -> dict[str, float | int]:
        """Return a JSON-serializable metric map."""
        return {
            "citation_correctness": self.citation_correctness,
            "citation_recall": self.citation_recall,
            "citation_precision": self.citation_precision,
            "missing_citation_count": self.missing_citation_count,
        }


def evaluate_citation_metrics(examples: list[EvaluationExample]) -> CitationMetrics:
    """Compute citation validity and expected-source coverage."""
    if not examples:
        return CitationMetrics(0.0, 0.0, 0.0, 0, ())

    validator = CitationValidator()
    correctness_scores: list[float] = []
    recall_scores: list[float] = []
    precision_scores: list[float] = []
    missing_total = 0
    per_example: list[CitationExampleResult] = []

    for example in examples:
        expected = set(example.expected_sources)
        available = set(example.retrieved_source_ids)
        cited = validator.extract_source_ids(example.answer)
        missing_source_ids: tuple[str, ...] = ()
        try:
            validator.validate(
                example.answer,
                available_source_ids=available,
                require_citation=bool(expected),
            )
            has_required_citation = bool(cited) or not expected
        except CitationValidationError as exc:
            missing_source_ids = exc.missing_source_ids
            has_required_citation = False

        cited_set = set(cited)
        uncited_expected = tuple(sorted(expected - cited_set))
        precision = len(cited_set & expected) / len(cited_set) if cited_set else 0.0
        recall = len(cited_set & expected) / len(expected) if expected else 1.0
        if not expected and not cited_set:
            precision = 1.0

        is_correct = not missing_source_ids and has_required_citation
        correctness_scores.append(1.0 if is_correct else 0.0)
        recall_scores.append(recall)
        precision_scores.append(precision)
        missing_total += len(missing_source_ids)
        per_example.append(
            CitationExampleResult(
                cited_source_ids=cited,
                missing_source_ids=tuple(sorted(missing_source_ids)),
                uncited_expected_sources=uncited_expected,
            )
        )

    return CitationMetrics(
        citation_correctness=_mean(correctness_scores),
        citation_recall=_mean(recall_scores),
        citation_precision=_mean(precision_scores),
        missing_citation_count=missing_total,
        examples=tuple(per_example),
    )


def _mean(values: list[float]) -> float:
    if not values:
        return 0.0
    return round(sum(values) / len(values), 4)
