"""Embedding provider protocol and contracts."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class EmbeddingProvider(Protocol):
    """Protocol for dense vector embedding generation."""

    @property
    def model_name(self) -> str:
        """Model identifier (e.g. 'BAAI/bge-m3', 'fake-1024')."""
        ...

    @property
    def dimension(self) -> int:
        """Vector dimensionality (e.g. 1024 for BGE-M3 dense)."""
        ...

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Generate dense vector embeddings for a list of document strings."""
        ...

    async def embed_query(self, text: str) -> list[float]:
        """Generate a dense vector embedding for a query string."""
        ...
