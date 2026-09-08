"""Dataset schema for deterministic RAG evaluation fixtures."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

SECRET_SHAPED_RE = re.compile(
    r"(sk-[A-Za-z0-9]{20,}|gh[po]_[A-Za-z0-9]{30,}|Bearer\s+[A-Za-z0-9._\-]{20,})"
)
SOURCE_ID_RE = re.compile(r"^\[S[1-9]\d*\]$")


class DatasetValidationError(ValueError):
    """Raised when an evaluation JSONL dataset violates the local schema."""


@dataclass(frozen=True)
class RetrievedSource:
    """One ranked source made available to an answer/citation evaluator."""

    source_id: str
    rank: int
    content: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EvaluationExample:
    """One fixture-safe evaluation example."""

    question: str
    expected_answer: str
    expected_sources: tuple[str, ...]
    metadata: dict[str, Any]
    retrieved_sources: tuple[RetrievedSource, ...] = ()
    answer: str = ""

    @property
    def retrieved_source_ids(self) -> tuple[str, ...]:
        """Return source IDs sorted by retrieval rank."""
        return tuple(source.source_id for source in sorted(self.retrieved_sources, key=_rank_key))

    def top_retrieved_source_ids(self, k: int) -> tuple[str, ...]:
        """Return the first k source IDs from the ranked retrieved context."""
        if k <= 0:
            return ()
        return self.retrieved_source_ids[:k]


def load_jsonl_dataset(path: Path) -> list[EvaluationExample]:
    """Load and validate an evaluation dataset from JSONL."""
    if not path.exists():
        raise DatasetValidationError(f"dataset file does not exist: {path}")

    examples: list[EvaluationExample] = []
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            raise DatasetValidationError(
                f"{path.name}:{line_number}: invalid JSON: {exc.msg}"
            ) from exc
        if not isinstance(payload, Mapping):
            raise DatasetValidationError(f"{path.name}:{line_number}: example must be an object")
        _reject_secret_shaped_values(payload, path.name, line_number)
        examples.append(_example_from_mapping(payload, path.name, line_number))

    if not examples:
        raise DatasetValidationError(f"{path.name}: dataset must contain at least one example")
    return examples


def dataset_name_from_path(path: Path) -> str:
    """Return the stable dataset name used in reports and API metadata."""
    return path.stem


def _example_from_mapping(
    payload: Mapping[str, Any],
    filename: str,
    line_number: int,
) -> EvaluationExample:
    question = _required_string(payload, "question", filename, line_number)
    expected_answer = _required_string(payload, "expected_answer", filename, line_number)
    expected_sources = _required_source_ids(payload, "expected_sources", filename, line_number)

    metadata = payload.get("metadata", {})
    if not isinstance(metadata, dict):
        raise DatasetValidationError(f"{filename}:{line_number}: metadata must be an object")

    retrieved_sources = _parse_retrieved_sources(
        payload.get("retrieved_sources", []), filename, line_number
    )
    answer_value = payload.get("answer")
    if answer_value is None:
        answer = f"{expected_answer} {' '.join(expected_sources)}".strip()
    elif isinstance(answer_value, str):
        answer = answer_value.strip()
    else:
        raise DatasetValidationError(f"{filename}:{line_number}: answer must be a string")
    if not answer:
        raise DatasetValidationError(f"{filename}:{line_number}: answer must not be empty")

    return EvaluationExample(
        question=question,
        expected_answer=expected_answer,
        expected_sources=expected_sources,
        metadata=dict(metadata),
        retrieved_sources=retrieved_sources,
        answer=answer,
    )


def _required_string(
    payload: Mapping[str, Any],
    field_name: str,
    filename: str,
    line_number: int,
) -> str:
    value = payload.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise DatasetValidationError(f"{filename}:{line_number}: {field_name} must be a string")
    return value.strip()


def _required_source_ids(
    payload: Mapping[str, Any],
    field_name: str,
    filename: str,
    line_number: int,
) -> tuple[str, ...]:
    value = payload.get(field_name)
    if not isinstance(value, list) or not value:
        raise DatasetValidationError(
            f"{filename}:{line_number}: {field_name} must be a non-empty list"
        )
    source_ids = tuple(_source_id(item, filename, line_number, field_name) for item in value)
    return tuple(dict.fromkeys(source_ids))


def _parse_retrieved_sources(
    value: object,
    filename: str,
    line_number: int,
) -> tuple[RetrievedSource, ...]:
    if not isinstance(value, list):
        raise DatasetValidationError(f"{filename}:{line_number}: retrieved_sources must be a list")
    sources: list[RetrievedSource] = []
    for index, item in enumerate(value, start=1):
        if isinstance(item, str):
            sources.append(
                RetrievedSource(source_id=_source_id(item, filename, line_number), rank=index)
            )
            continue
        if not isinstance(item, Mapping):
            raise DatasetValidationError(
                f"{filename}:{line_number}: retrieved_sources[{index}] must be an object"
            )
        source_id = _source_id(item.get("source_id"), filename, line_number, "source_id")
        rank_value = item.get("rank", index)
        if not isinstance(rank_value, int) or rank_value < 1:
            raise DatasetValidationError(
                f"{filename}:{line_number}: retrieved_sources[{index}].rank must be positive"
            )
        content = item.get("content", "")
        if not isinstance(content, str):
            raise DatasetValidationError(
                f"{filename}:{line_number}: retrieved_sources[{index}].content must be a string"
            )
        metadata = item.get("metadata", {})
        if not isinstance(metadata, dict):
            raise DatasetValidationError(
                f"{filename}:{line_number}: retrieved_sources[{index}].metadata must be an object"
            )
        sources.append(
            RetrievedSource(
                source_id=source_id,
                rank=rank_value,
                content=content.strip(),
                metadata=dict(metadata),
            )
        )
    return tuple(sorted(sources, key=_rank_key))


def _source_id(
    value: object,
    filename: str,
    line_number: int,
    field_name: str = "source_id",
) -> str:
    if not isinstance(value, str) or not SOURCE_ID_RE.match(value.strip()):
        raise DatasetValidationError(
            f"{filename}:{line_number}: {field_name} must look like [S1], [S2], ..."
        )
    return value.strip()


def _reject_secret_shaped_values(value: object, filename: str, line_number: int) -> None:
    if isinstance(value, str) and SECRET_SHAPED_RE.search(value):
        raise DatasetValidationError(f"{filename}:{line_number}: credential-shaped value detected")
    if isinstance(value, Mapping):
        for nested in value.values():
            _reject_secret_shaped_values(nested, filename, line_number)
    elif isinstance(value, list):
        for nested in value:
            _reject_secret_shaped_values(nested, filename, line_number)


def _rank_key(source: RetrievedSource) -> tuple[int, str]:
    return source.rank, source.source_id
