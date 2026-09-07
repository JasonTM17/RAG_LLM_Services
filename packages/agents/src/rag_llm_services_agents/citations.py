"""Citation validation shared by chat, RAG, and study workflows."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

from rag_llm_services_rag.retrieval.types import CitedChunk, ContextBundle

_CITATION_PATTERN = re.compile(r"\[S[1-9]\d*\]")


class CitationValidationError(ValueError):
    """Raised when model output cites a source that was not provided."""

    def __init__(
        self,
        message: str,
        *,
        missing_source_ids: Iterable[str] = (),
        available_source_ids: Iterable[str] = (),
    ) -> None:
        super().__init__(message)
        self.missing_source_ids = tuple(sorted(set(missing_source_ids)))
        self.available_source_ids = tuple(sorted(set(available_source_ids)))


@dataclass(frozen=True)
class CitationValidationResult:
    """Normalized citation validation details."""

    cited_source_ids: tuple[str, ...]
    available_source_ids: tuple[str, ...]
    missing_source_ids: tuple[str, ...]

    @property
    def is_valid(self) -> bool:
        return not self.missing_source_ids


class CitationValidator:
    """Validate bracketed source IDs against a bounded context bundle."""

    def extract_source_ids(self, text: str) -> tuple[str, ...]:
        """Return unique source IDs in first-seen order."""
        seen: set[str] = set()
        ordered: list[str] = []
        for match in _CITATION_PATTERN.findall(text):
            if match not in seen:
                seen.add(match)
                ordered.append(match)
        return tuple(ordered)

    def validate(
        self,
        answer: str,
        context_bundle: ContextBundle | None = None,
        *,
        available_source_ids: Iterable[str] | None = None,
        require_citation: bool = False,
    ) -> CitationValidationResult:
        """Reject invented citations and optionally require at least one citation."""
        available = (
            tuple(chunk.source_id for chunk in context_bundle.cited_chunks)
            if context_bundle is not None
            else tuple(available_source_ids or ())
        )
        cited = self.extract_source_ids(answer)
        missing = tuple(source_id for source_id in cited if source_id not in set(available))
        if missing:
            raise CitationValidationError(
                "Model output cited unavailable sources: " + ", ".join(missing),
                missing_source_ids=missing,
                available_source_ids=available,
            )
        if require_citation and available and not cited:
            raise CitationValidationError(
                "Model output must cite at least one provided source",
                available_source_ids=available,
            )
        return CitationValidationResult(
            cited_source_ids=cited,
            available_source_ids=tuple(available),
            missing_source_ids=missing,
        )

    def validate_source_ids(
        self,
        source_ids: Iterable[str],
        context_bundle: ContextBundle | None = None,
        *,
        available_source_ids: Iterable[str] | None = None,
        require_citation: bool = False,
    ) -> CitationValidationResult:
        """Validate a structured output field containing source IDs."""
        rendered = " ".join(source_ids)
        return self.validate(
            rendered,
            context_bundle,
            available_source_ids=available_source_ids,
            require_citation=require_citation,
        )

    def cited_chunks(self, answer: str, context_bundle: ContextBundle | None) -> list[CitedChunk]:
        """Return context chunks actually cited by the answer after validation."""
        if context_bundle is None:
            self.validate(answer, context_bundle)
            return []
        result = self.validate(answer, context_bundle)
        cited_ids = set(result.cited_source_ids)
        return [chunk for chunk in context_bundle.cited_chunks if chunk.source_id in cited_ids]
