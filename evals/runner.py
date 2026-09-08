"""Evaluation runner for fixture-safe RAG quality gates."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from evals.evaluators.answer_metrics import evaluate_answer_metrics
from evals.evaluators.citation_metrics import evaluate_citation_metrics
from evals.evaluators.retrieval_metrics import evaluate_retrieval_metrics
from evals.schema import EvaluationExample, dataset_name_from_path, load_jsonl_dataset

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET_PATH = REPO_ROOT / "evals" / "datasets" / "baseline-learning-rag.jsonl"
DEFAULT_REPORTS_DIR = REPO_ROOT / "evals" / "reports" / "local"


@dataclass(frozen=True)
class EvaluationThresholds:
    """Regression thresholds for deterministic evaluation metrics."""

    retrieval_hit_rate: float = 1.0
    recall_at_k: float = 0.8
    mrr: float = 0.8
    ndcg_at_k: float = 0.8
    context_relevance: float = 0.5
    answer_relevance: float = 0.65
    citation_correctness: float = 1.0
    citation_recall: float = 0.8
    faithfulness: float = 0.6

    @classmethod
    def from_env(cls) -> EvaluationThresholds:
        """Build thresholds from environment variables with safe defaults."""
        return cls(
            retrieval_hit_rate=_env_float("EVAL_RETRIEVAL_HIT_RATE_THRESHOLD", 1.0),
            recall_at_k=_env_float("EVAL_RECALL_AT_K_THRESHOLD", 0.8),
            mrr=_env_float("EVAL_MRR_THRESHOLD", 0.8),
            ndcg_at_k=_env_float("EVAL_NDCG_AT_K_THRESHOLD", 0.8),
            context_relevance=_env_float("EVAL_CONTEXT_RELEVANCE_THRESHOLD", 0.5),
            answer_relevance=_env_float("EVAL_ANSWER_RELEVANCE_THRESHOLD", 0.65),
            citation_correctness=_env_float("EVAL_CITATION_CORRECTNESS_THRESHOLD", 1.0),
            citation_recall=_env_float("EVAL_CITATION_RECALL_THRESHOLD", 0.8),
            faithfulness=_env_float("EVAL_FAITHFULNESS_THRESHOLD", 0.6),
        )

    def as_dict(self) -> dict[str, float]:
        """Return thresholds as a metric-name keyed map."""
        return {
            "retrieval_hit_rate": self.retrieval_hit_rate,
            "recall_at_k": self.recall_at_k,
            "mrr": self.mrr,
            "ndcg_at_k": self.ndcg_at_k,
            "context_relevance": self.context_relevance,
            "answer_relevance": self.answer_relevance,
            "citation_correctness": self.citation_correctness,
            "citation_recall": self.citation_recall,
            "faithfulness": self.faithfulness,
        }


@dataclass(frozen=True)
class EvaluationRunResult:
    """Result returned by a completed evaluation run."""

    status: str
    dataset_name: str
    example_count: int
    top_k: int
    metrics: dict[str, float | int]
    thresholds: dict[str, float]
    failures: tuple[str, ...]
    report_json_path: Path | None = None
    report_markdown_path: Path | None = None

    def as_metadata(self) -> dict[str, Any]:
        """Return JSON-safe metadata for API persistence."""
        return {
            "result": {
                "status": self.status,
                "dataset_name": self.dataset_name,
                "example_count": self.example_count,
                "top_k": self.top_k,
                "metrics": self.metrics,
                "thresholds": self.thresholds,
                "failures": list(self.failures),
                "report_json_path": _path_as_posix(self.report_json_path),
                "report_markdown_path": _path_as_posix(self.report_markdown_path),
            }
        }


def run_evaluation(
    *,
    dataset_path: Path = DEFAULT_DATASET_PATH,
    reports_dir: Path = DEFAULT_REPORTS_DIR,
    thresholds: EvaluationThresholds | None = None,
    top_k: int | None = None,
    write_report: bool = True,
) -> EvaluationRunResult:
    """Run deterministic fixture evaluation and optionally write reports."""
    effective_top_k = top_k if top_k is not None else _env_int("EVAL_TOP_K", 5)
    if effective_top_k < 1:
        raise ValueError("top_k must be at least 1")
    effective_thresholds = thresholds or EvaluationThresholds.from_env()
    examples = load_jsonl_dataset(dataset_path)
    dataset_name = dataset_name_from_path(dataset_path)

    retrieval = evaluate_retrieval_metrics(examples, k=effective_top_k)
    citations = evaluate_citation_metrics(examples)
    answers = evaluate_answer_metrics(examples)
    metrics: dict[str, float | int] = {
        **retrieval.as_dict(),
        **citations.as_dict(),
        **answers.as_dict(),
    }
    threshold_map = effective_thresholds.as_dict()
    failures = tuple(
        f"{metric_name}={float(metrics[metric_name]):.4f} below threshold {threshold:.4f}"
        for metric_name, threshold in threshold_map.items()
        if float(metrics.get(metric_name, 0.0)) < threshold
    )
    status = "PASS" if not failures else "FAIL"

    result = EvaluationRunResult(
        status=status,
        dataset_name=dataset_name,
        example_count=len(examples),
        top_k=effective_top_k,
        metrics=metrics,
        thresholds=threshold_map,
        failures=failures,
    )
    if write_report:
        report_json_path, report_markdown_path = _write_reports(
            reports_dir=reports_dir,
            result=result,
            examples=examples,
        )
        result = EvaluationRunResult(
            status=result.status,
            dataset_name=result.dataset_name,
            example_count=result.example_count,
            top_k=result.top_k,
            metrics=result.metrics,
            thresholds=result.thresholds,
            failures=result.failures,
            report_json_path=report_json_path,
            report_markdown_path=report_markdown_path,
        )
    return result


def _write_reports(
    *,
    reports_dir: Path,
    result: EvaluationRunResult,
    examples: list[EvaluationExample],
) -> tuple[Path, Path]:
    reports_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    stem = f"{timestamp}-{result.dataset_name}"
    json_path = reports_dir / f"{stem}.json"
    markdown_path = reports_dir / f"{stem}.md"

    json_payload = {
        "status": result.status,
        "dataset_name": result.dataset_name,
        "example_count": result.example_count,
        "top_k": result.top_k,
        "metrics": result.metrics,
        "thresholds": result.thresholds,
        "failures": list(result.failures),
        "examples": [
            _safe_example_summary(example, index) for index, example in enumerate(examples, 1)
        ],
    }
    json_path.write_text(
        json.dumps(json_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    markdown_path.write_text(_markdown_report(result), encoding="utf-8")
    return json_path, markdown_path


def _safe_example_summary(example: EvaluationExample, index: int) -> dict[str, Any]:
    return {
        "index": index,
        "metadata": example.metadata,
        "expected_sources": list(example.expected_sources),
        "retrieved_sources": list(example.retrieved_source_ids),
    }


def _markdown_report(result: EvaluationRunResult) -> str:
    lines = [
        f"# RAG Evaluation Report: {result.dataset_name}",
        "",
        f"- Status: {result.status}",
        f"- Examples: {result.example_count}",
        f"- Top K: {result.top_k}",
        "",
        "## Metrics",
        "",
    ]
    for metric_name, value in sorted(result.metrics.items()):
        lines.append(f"- {metric_name}: {value}")
    lines.extend(["", "## Thresholds", ""])
    for metric_name, value in sorted(result.thresholds.items()):
        lines.append(f"- {metric_name}: {value}")
    lines.extend(["", "## Failures", ""])
    if result.failures:
        lines.extend(f"- {failure}" for failure in result.failures)
    else:
        lines.append("- none")
    lines.append("")
    return "\n".join(lines)


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    value = float(raw)
    if not 0.0 <= value <= 1.0:
        raise ValueError(f"{name} must be between 0.0 and 1.0")
    return value


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    return int(raw)


def _path_as_posix(path: Path | None) -> str | None:
    if path is None:
        return None
    try:
        return path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.name
