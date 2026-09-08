"""Security abuse tests for citation validation."""

from __future__ import annotations

import uuid

import pytest

from rag_llm_services_agents.citations import CitationValidationError, CitationValidator
from rag_llm_services_rag.retrieval.types import CitedChunk, ContextBundle


def _bundle() -> ContextBundle:
    return ContextBundle(
        context_text="[S1] Source: doc.md\nGrounded fact.",
        cited_chunks=[
            CitedChunk(
                source_id="[S1]",
                chunk_id=uuid.uuid4(),
                document_id=uuid.uuid4(),
                content="Grounded fact.",
            )
        ],
    )


def test_duplicate_citations_are_normalized_without_rejecting_valid_answer() -> None:
    result = CitationValidator().validate("Grounded [S1]. Still grounded [S1].", _bundle())

    assert result.cited_source_ids == ("[S1]",)


def test_mixed_valid_and_missing_citations_are_rejected() -> None:
    with pytest.raises(CitationValidationError) as excinfo:
        CitationValidator().validate("Grounded [S1], invented [S2].", _bundle())

    assert excinfo.value.missing_source_ids == ("[S2]",)


def test_structured_citation_field_rejects_unavailable_source_id() -> None:
    with pytest.raises(CitationValidationError):
        CitationValidator().validate_source_ids(["[S9]"], _bundle(), require_citation=True)
