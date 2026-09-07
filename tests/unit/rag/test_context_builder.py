"""Unit tests for ContextBuilder citation generation and token budgeting."""

from __future__ import annotations

import uuid

from rag_llm_services_rag.retrieval.context import ContextBuilder, format_source_header
from rag_llm_services_rag.retrieval.types import (
    RetrievalMethod,
    RetrievalResult,
)


def _make_result(
    content: str,
    filename: str = "doc.txt",
    page: int | None = None,
    section: str | None = None,
    score: float = 0.9,
    rank: int = 1,
) -> RetrievalResult:
    return RetrievalResult(
        chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        content=content,
        score=score,
        retrieval_method=RetrievalMethod.HYBRID,
        filename=filename,
        page=page,
        section=section,
        rank=rank,
    )


def test_format_source_header() -> None:
    h1 = format_source_header("[S1]", "manual.pdf", page=3, section="Introduction")
    assert h1 == "[S1] Source: manual.pdf (Page 3, Section: Introduction)"

    h2 = format_source_header("[S2]", "readme.md", section="Setup")
    assert h2 == "[S2] Source: readme.md (Section: Setup)"

    h3 = format_source_header("[S3]", "data.txt", page=1)
    assert h3 == "[S3] Source: data.txt (Page 1)"

    h4 = format_source_header("[S4]", "")
    assert h4 == "[S4] Source: document"


def test_context_builder_labels_citations_sequentially() -> None:
    builder = ContextBuilder(default_max_budget=5000)
    candidates = [
        _make_result("First paragraph of content", filename="report.pdf", page=1, rank=1),
        _make_result(
            "Second paragraph of content", filename="spec.md", section="Architecture", rank=2
        ),
    ]

    bundle = builder.build(candidates)

    assert bundle.total_chunks == 2
    assert len(bundle.cited_chunks) == 2
    assert bundle.cited_chunks[0].source_id == "[S1]"
    assert bundle.cited_chunks[0].filename == "report.pdf"
    assert bundle.cited_chunks[0].page == 1

    assert bundle.cited_chunks[1].source_id == "[S2]"
    assert bundle.cited_chunks[1].filename == "spec.md"
    assert bundle.cited_chunks[1].section == "Architecture"

    assert "[S1] Source: report.pdf" in bundle.context_text
    assert "[S2] Source: spec.md" in bundle.context_text
    assert "First paragraph of content" in bundle.context_text
    assert "Second paragraph of content" in bundle.context_text


def test_context_builder_strictly_enforces_token_budget() -> None:
    """Chunks that would cause the total token count to exceed budget are excluded."""
    builder = ContextBuilder()

    # Create 5 chunks of ~30 tokens each
    content_chunk = (
        "Đây là đoạn văn bản kiểm thử giới hạn ngân sách token của bộ tạo ngữ cảnh ContextBuilder."
    )
    candidates = [_make_result(f"{content_chunk} Số thứ tự: {i}", rank=i) for i in range(1, 6)]

    # If we set a very tight budget (e.g. 50 tokens), only 1 chunk should fit
    bundle_small = builder.build(candidates, max_budget=50)
    assert bundle_small.total_chunks == 1
    assert bundle_small.total_tokens <= 50
    assert len(bundle_small.cited_chunks) == 1
    assert bundle_small.cited_chunks[0].source_id == "[S1]"

    # If budget allows 3 chunks
    bundle_medium = builder.build(candidates, max_budget=120)
    assert bundle_medium.total_chunks >= 2
    assert bundle_medium.total_tokens <= 120


def test_context_builder_empty_input() -> None:
    builder = ContextBuilder(default_max_budget=2000)
    bundle = builder.build([])

    assert bundle.context_text == ""
    assert bundle.cited_chunks == []
    assert bundle.total_tokens == 0
    assert bundle.total_chunks == 0
    assert bundle.max_budget == 2000


def test_context_builder_budget_smaller_than_first_chunk() -> None:
    builder = ContextBuilder()
    long_content = "Word " * 200
    candidates = [_make_result(long_content)]

    # Budget of only 5 tokens cannot fit the 200-word chunk
    bundle = builder.build(candidates, max_budget=5)
    assert bundle.total_chunks == 0
    assert bundle.context_text == ""
    assert bundle.total_tokens == 0
