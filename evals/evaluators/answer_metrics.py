"""Deterministic answer relevance and faithfulness metrics."""

from __future__ import annotations

import re
from dataclasses import dataclass

from evals.schema import EvaluationExample
from rag_llm_services_agents.citations import CitationValidator

TOKEN_RE = re.compile(r"[a-z0-9]+")
CITATION_MARKER_RE = re.compile(r"\s*\[S[1-9]\d*\]")
STOPWORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "by",
        "for",
        "from",
        "in",
        "is",
        "of",
        "on",
        "or",
        "the",
        "to",
        "with",
    }
)


@dataclass(frozen=True)
class AnswerMetrics:
    """Aggregate deterministic answer quality metric values."""

    answer_relevance: float
    faithfulness: float

    def as_dict(self) -> dict[str, float]:
        """Return a JSON-serializable metric map."""
        return {
            "answer_relevance": self.answer_relevance,
            "faithfulness": self.faithfulness,
        }


def evaluate_answer_metrics(examples: list[EvaluationExample]) -> AnswerMetrics:
    """Compute token-overlap answer relevance and groundedness."""
    if not examples:
        return AnswerMetrics(0.0, 0.0)

    validator = CitationValidator()
    relevance_scores: list[float] = []
    faithfulness_scores: list[float] = []
    for example in examples:
        relevance_scores.append(_token_f1(example.answer, example.expected_answer))
        cited = set(validator.extract_source_ids(example.answer))
        grounding_sources = [
            source.content
            for source in example.retrieved_sources
            if not cited or source.source_id in cited
        ]
        faithfulness_scores.append(_token_recall(example.answer, " ".join(grounding_sources)))

    return AnswerMetrics(
        answer_relevance=_mean(relevance_scores),
        faithfulness=_mean(faithfulness_scores),
    )


def _token_f1(candidate: str, reference: str) -> float:
    candidate_tokens = _tokens(candidate)
    reference_tokens = _tokens(reference)
    if not candidate_tokens or not reference_tokens:
        return 0.0
    overlap = len(candidate_tokens & reference_tokens)
    if overlap == 0:
        return 0.0
    precision = overlap / len(candidate_tokens)
    recall = overlap / len(reference_tokens)
    return round((2 * precision * recall) / (precision + recall), 4)


def _token_recall(candidate: str, grounding_text: str) -> float:
    candidate_tokens = _tokens(candidate)
    grounding_tokens = _tokens(grounding_text)
    if not candidate_tokens:
        return 0.0
    if not grounding_tokens:
        return 0.0
    return round(len(candidate_tokens & grounding_tokens) / len(candidate_tokens), 4)


def _tokens(value: str) -> set[str]:
    value = CITATION_MARKER_RE.sub(" ", value)
    return {token for token in TOKEN_RE.findall(value.lower()) if token not in STOPWORDS}


def _mean(values: list[float]) -> float:
    if not values:
        return 0.0
    return round(sum(values) / len(values), 4)
