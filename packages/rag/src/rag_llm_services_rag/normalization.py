"""Text normalization for RAG ingestion: Unicode NFC, Vietnamese diacritics, whitespace, linebreaks."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import replace

from rag_llm_services_rag.parsers.base import ParsedSection

# Non-printable control characters excluding \t and \n
_CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")

# Zero-width spaces, soft hyphens, and byte order marks
_ZERO_WIDTH_RE = re.compile(r"[\u200b\u200c\u200d\ufeff\u00ad]")

# Repeated whitespace inside lines
_INLINE_WHITESPACE_RE = re.compile(r"[^\S\n\r]+")

# Multiple consecutive blank lines
_CONSECUTIVE_BLANK_LINES_RE = re.compile(r"\n{3,}")


def normalize_text(text: str) -> str:
    """Normalize input text for consistent chunking, embedding, and retrieval.

    - Decomposes and recomposes Unicode to Canonical Composition (NFC), crucial
      for Vietnamese decomposed vs precomposed diacritics.
    - Strips unprintable control characters and zero-width spaces.
    - Standardizes CRLF and CR line endings to LF.
    - Collapses repeated blank lines to double newlines (preserving paragraphs).
    - Normalizes inline whitespace (spaces/tabs/non-breaking spaces).
    """
    if not text:
        return ""

    # 1. Normalize Unicode to NFC
    normalized = unicodedata.normalize("NFC", text)

    # 2. Replace non-breaking spaces (\u00a0, \u202f) with regular space
    normalized = normalized.replace("\u00a0", " ").replace("\u202f", " ")

    # 3. Strip zero-width and invisible characters
    normalized = _ZERO_WIDTH_RE.sub("", normalized)

    # 4. Strip control characters (preserving \n and \t)
    normalized = _CONTROL_CHAR_RE.sub("", normalized)

    # 5. Standardize line endings to \n
    normalized = normalized.replace("\r\n", "\n").replace("\r", "\n")

    # 6. Normalize inline whitespace per line and strip line ends
    lines = [_INLINE_WHITESPACE_RE.sub(" ", line).rstrip() for line in normalized.split("\n")]
    normalized = "\n".join(lines)

    # 7. Collapse 3+ newlines to 2 newlines (paragraphs preserved)
    normalized = _CONSECUTIVE_BLANK_LINES_RE.sub("\n\n", normalized)

    return normalized.strip()


class TextNormalizer:
    """Normalizer service for strings and parsed document sections."""

    def __init__(self, unicode_form: str = "NFC") -> None:
        self.unicode_form = unicode_form

    def normalize(self, text: str) -> str:
        """Normalize a raw string."""
        return normalize_text(text)

    def normalize_sections(self, sections: list[ParsedSection]) -> list[ParsedSection]:
        """Normalize all sections while preserving structural metadata and hierarchy."""
        normalized_sections: list[ParsedSection] = []
        for section in sections:
            clean_content = self.normalize(section.content)
            if not clean_content:
                continue

            clean_header = (
                self.normalize(section.section_header) if section.section_header else None
            )
            clean_hierarchy = [self.normalize(h) for h in section.hierarchy]

            normalized_sections.append(
                replace(
                    section,
                    content=clean_content,
                    section_header=clean_header,
                    hierarchy=clean_hierarchy,
                )
            )
        return normalized_sections
