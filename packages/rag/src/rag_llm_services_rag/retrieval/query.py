"""Query normalization for lexical and semantic retrieval."""

from __future__ import annotations

import re
import unicodedata

_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_WHITESPACE_RE = re.compile(r"\s+")


def normalize_query(query: str) -> str:
    """Normalize a user search query for vector and full-text search.

    Performs:
    1. Unicode NFC normalization (preserving Vietnamese accents and CJK characters).
    2. Removal of unprintable ASCII control characters.
    3. Trimming and collapse of redundant whitespace.
    4. Balancing of double-quotes to ensure valid syntax for PostgreSQL websearch_to_tsquery.
    """
    if not query:
        return ""

    # 1. Unicode NFC normalization
    normalized = unicodedata.normalize("NFC", query)

    # 2. Strip control characters
    normalized = _CONTROL_CHARS_RE.sub(" ", normalized)

    # 3. Collapse whitespace
    normalized = _WHITESPACE_RE.sub(" ", normalized).strip()

    if not normalized:
        return ""

    # 4. Handle unbalanced double quotes for PostgreSQL websearch_to_tsquery
    quote_count = normalized.count('"')
    if quote_count % 2 != 0:
        # Strip the last dangling quote or unbalanced quote
        last_quote_idx = normalized.rfind('"')
        normalized = (normalized[:last_quote_idx] + normalized[last_quote_idx + 1 :]).strip()

    return _WHITESPACE_RE.sub(" ", normalized).strip()


class QueryNormalizer:
    """Configurable query normalizer service."""

    def __init__(self, max_length: int = 2000) -> None:
        self.max_length = max_length

    def normalize(self, query: str) -> str:
        """Normalize and length-bound the user search query."""
        cleaned = normalize_query(query)
        if len(cleaned) > self.max_length:
            cleaned = cleaned[: self.max_length].strip()
        return cleaned
