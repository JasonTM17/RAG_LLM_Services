"""Semantic-aware recursive chunker with citation metadata and header hierarchy preservation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from rag_llm_services_rag.parsers.base import ParsedDocument

# Standard hierarchy of text separators for recursive splitting
DEFAULT_SEPARATORS: list[str] = [
    "\n\n",  # Paragraphs
    "\n",  # Lines
    ". ",  # English/Vietnamese sentence ends
    "? ",
    "! ",
    "; ",
    ", ",  # Clauses
    " ",  # Words
    "",  # Character fallback
]


def default_token_estimator(text: str) -> int:
    """Estimate token count for multilingual / Vietnamese text.

    Uses word count + punctuation estimation, suitable for BGE-M3 / BERT tokenizers
    without requiring heavy tokenizer library load.
    """
    if not text.strip():
        return 0
    words = text.split()
    # Approx 1.2 to 1.3 subword tokens per word on average for multilingual text
    return max(1, int(len(words) * 1.25))


@dataclass(frozen=True)
class ChunkPayload:
    """A semantic chunk prepared for embedding and persistence."""

    content: str
    chunk_index: int
    token_count: int
    metadata: dict[str, Any] = field(default_factory=dict)


class Chunker:
    """Recursive semantic chunker preserving citation metadata and header hierarchy."""

    def __init__(
        self,
        chunk_size: int = 512,
        chunk_overlap: int = 64,
        separators: list[str] | None = None,
        length_function: Callable[[str], int] | None = None,
    ) -> None:
        if chunk_size <= 0:
            raise ValueError("chunk_size must be positive")
        if chunk_overlap < 0:
            raise ValueError("chunk_overlap must be non-negative")
        if chunk_overlap >= chunk_size:
            raise ValueError("chunk_overlap must be strictly smaller than chunk_size")

        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.separators = separators or list(DEFAULT_SEPARATORS)
        self.length_function = length_function or default_token_estimator

    def chunk_document(self, document: ParsedDocument) -> list[ChunkPayload]:
        """Split a structured ParsedDocument into chunks preserving page and heading metadata."""
        all_chunks: list[ChunkPayload] = []
        global_index = 0

        # If document has structured sections (from pages or headings), chunk per section
        if document.sections:
            for section in document.sections:
                section_metadata: dict[str, Any] = dict(document.metadata)
                section_metadata.update(section.metadata)

                if section.page_number is not None:
                    section_metadata["page_number"] = section.page_number
                if section.section_header:
                    section_metadata["section_header"] = section.section_header
                if section.hierarchy:
                    section_metadata["hierarchy"] = section.hierarchy

                section_chunks = self.chunk_text(
                    section.content,
                    base_metadata=section_metadata,
                    start_index=global_index,
                )
                all_chunks.extend(section_chunks)
                global_index += len(section_chunks)
        elif document.raw_text.strip():
            all_chunks = self.chunk_text(
                document.raw_text,
                base_metadata=document.metadata,
                start_index=0,
            )

        return all_chunks

    def chunk_text(
        self,
        text: str,
        base_metadata: dict[str, Any] | None = None,
        start_index: int = 0,
    ) -> list[ChunkPayload]:
        """Recursively split raw text into overlapping semantic chunks."""
        clean_text = text.strip()
        if not clean_text:
            return []

        # If text fits entirely within one chunk
        if self.length_function(clean_text) <= self.chunk_size:
            meta = dict(base_metadata or {})
            meta["chunk_index"] = start_index
            return [
                ChunkPayload(
                    content=clean_text,
                    chunk_index=start_index,
                    token_count=self.length_function(clean_text),
                    metadata=meta,
                )
            ]

        raw_splits = self._recursive_split(clean_text, self.separators)
        merged_chunks = self._merge_splits(raw_splits)

        results: list[ChunkPayload] = []
        for offset, chunk_text in enumerate(merged_chunks):
            idx = start_index + offset
            meta = dict(base_metadata or {})
            meta["chunk_index"] = idx
            results.append(
                ChunkPayload(
                    content=chunk_text,
                    chunk_index=idx,
                    token_count=self.length_function(chunk_text),
                    metadata=meta,
                )
            )
        return results

    def _recursive_split(self, text: str, separators: list[str]) -> list[str]:
        """Split text recursively using the most specific separator that fits."""
        final_chunks: list[str] = []
        separator = separators[-1]
        new_separators: list[str] = []

        for i, sep in enumerate(separators):
            if sep == "":
                separator = ""
                break
            if sep in text:
                separator = sep
                new_separators = separators[i + 1 :]
                break

        splits = text.split(separator) if separator != "" else list(text)

        good_splits: list[str] = []
        for s in splits:
            if not s:
                continue
            if self.length_function(s) < self.chunk_size:
                good_splits.append(s)
            else:
                if good_splits:
                    final_chunks.extend(good_splits)
                    good_splits = []
                if not new_separators:
                    # Can't split further, must use as is
                    final_chunks.append(s)
                else:
                    sub_splits = self._recursive_split(s, new_separators)
                    final_chunks.extend(sub_splits)

        if good_splits:
            final_chunks.extend(good_splits)

        return final_chunks

    def _merge_splits(self, splits: list[str]) -> list[str]:
        """Merge smaller splits into chunks up to chunk_size, applying chunk_overlap."""
        merged: list[str] = []
        current_chunk: list[str] = []
        current_len = 0

        for s in splits:
            s_len = self.length_function(s)

            if current_len + s_len > self.chunk_size and current_chunk:
                merged_str = " ".join(current_chunk).strip()
                if merged_str:
                    merged.append(merged_str)

                # Keep overlap pieces from the tail of current_chunk
                overlap_chunk: list[str] = []
                overlap_len = 0
                for piece in reversed(current_chunk):
                    p_len = self.length_function(piece)
                    if overlap_len + p_len <= self.chunk_overlap:
                        overlap_chunk.insert(0, piece)
                        overlap_len += p_len
                    else:
                        break

                current_chunk = overlap_chunk
                current_len = overlap_len

            current_chunk.append(s)
            current_len += s_len

        if current_chunk:
            final_str = " ".join(current_chunk).strip()
            if final_str:
                merged.append(final_str)

        return merged
