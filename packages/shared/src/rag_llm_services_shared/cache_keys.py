"""Cache-key helpers that avoid raw user text and preserve owner scope."""

from __future__ import annotations

import hashlib
from uuid import UUID


def stable_sha256(value: str) -> str:
    """Return a lowercase SHA-256 hex digest for sensitive key material."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def retrieval_cache_key(
    *,
    owner_id: UUID,
    query: str,
    knowledge_base_id: UUID | None = None,
    document_ids: list[UUID] | None = None,
    version: str = "v1",
) -> str:
    """Build a retrieval cache key without embedding raw user query text."""
    scope_parts = [
        f"owner:{owner_id}",
        f"kb:{knowledge_base_id}" if knowledge_base_id else "kb:any",
        "docs:" + ",".join(sorted(str(doc_id) for doc_id in document_ids or [])),
        f"q:{stable_sha256(query.strip().lower())}",
    ]
    return "rag:retrieval:" + version + ":" + stable_sha256("|".join(scope_parts))
