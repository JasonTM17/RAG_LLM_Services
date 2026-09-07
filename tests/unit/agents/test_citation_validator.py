"""Citation validator tests."""

from __future__ import annotations

import uuid

import pytest

from rag_llm_services_agents.citations import CitationValidationError, CitationValidator
from rag_llm_services_rag.retrieval.types import CitedChunk, ContextBundle


def _context_bundle() -> ContextBundle:
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


def test_validator_accepts_available_source_ids() -> None:
    result = CitationValidator().validate("This is grounded [S1].", _context_bundle())

    assert result.is_valid is True
    assert result.cited_source_ids == ("[S1]",)


def test_validator_rejects_invented_source_ids() -> None:
    with pytest.raises(CitationValidationError) as excinfo:
        CitationValidator().validate("This cites a missing source [S9].", _context_bundle())

    assert excinfo.value.missing_source_ids == ("[S9]",)
    assert excinfo.value.available_source_ids == ("[S1]",)


def test_validator_can_require_a_citation_when_context_exists() -> None:
    with pytest.raises(CitationValidationError):
        CitationValidator().validate("No citation here.", _context_bundle(), require_citation=True)
