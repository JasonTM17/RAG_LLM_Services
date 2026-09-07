"""Context builder for token-bounded, source-rich context bundles with citation markers."""

from __future__ import annotations

from collections.abc import Callable

from rag_llm_services_rag.chunking import default_token_estimator
from rag_llm_services_rag.retrieval.types import (
    CitedChunk,
    ContextBundle,
    RetrievalResult,
)


def format_source_header(
    source_id: str,
    filename: str,
    page: int | None = None,
    section: str | None = None,
) -> str:
    """Build standardized citation source header string."""
    name = filename.strip() if filename else "document"
    header = f"{source_id} Source: {name}"
    details: list[str] = []
    if page is not None:
        details.append(f"Page {page}")
    if section and section.strip():
        details.append(f"Section: {section.strip()}")
    if details:
        header += f" ({', '.join(details)})"
    return header


class ContextBuilder:
    """Assembles ranked retrieval results into a bounded, source-tagged ContextBundle."""

    def __init__(
        self,
        default_max_budget: int = 6000,
        token_estimator: Callable[[str], int] | None = None,
    ) -> None:
        self.default_max_budget = default_max_budget
        self.token_estimator = token_estimator or default_token_estimator

    def build(
        self,
        candidates: list[RetrievalResult],
        max_budget: int | None = None,
    ) -> ContextBundle:
        """Assemble top ranked chunks into a bounded ContextBundle with [S1], [S2] markers."""
        budget = (
            max_budget if max_budget is not None and max_budget > 0 else self.default_max_budget
        )

        if not candidates:
            return ContextBundle(
                context_text="",
                cited_chunks=[],
                total_tokens=0,
                total_chunks=0,
                max_budget=budget,
            )

        cited_chunks: list[CitedChunk] = []
        formatted_blocks: list[str] = []
        accumulated_tokens = 0

        for idx, candidate in enumerate(candidates, start=1):
            source_id = f"[S{idx}]"
            header = format_source_header(
                source_id=source_id,
                filename=candidate.filename,
                page=candidate.page,
                section=candidate.section,
            )
            block = f"{header}\n{candidate.content.strip()}"
            block_tokens = self.token_estimator(block)

            # Account for separator tokens between blocks
            separator_tokens = self.token_estimator("\n\n") if formatted_blocks else 0
            if accumulated_tokens + separator_tokens + block_tokens > budget:
                # Token budget exhausted; stop adding further chunks
                break

            accumulated_tokens += separator_tokens + block_tokens
            formatted_blocks.append(block)

            cited = CitedChunk(
                source_id=source_id,
                chunk_id=candidate.chunk_id,
                document_id=candidate.document_id,
                content=candidate.content,
                filename=candidate.filename,
                page=candidate.page,
                section=candidate.section,
                token_count=block_tokens,
                score=candidate.score,
                retrieval_method=candidate.retrieval_method,
                metadata=dict(candidate.metadata),
            )
            cited_chunks.append(cited)

        context_text = "\n\n".join(formatted_blocks)
        total_tokens = self.token_estimator(context_text) if context_text else 0

        return ContextBundle(
            context_text=context_text,
            cited_chunks=cited_chunks,
            total_tokens=total_tokens,
            total_chunks=len(cited_chunks),
            max_budget=budget,
        )
