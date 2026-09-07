"""Deterministic zero-dependency fake embedding provider for hermetic testing."""

from __future__ import annotations

import asyncio
import hashlib
import math
import random

from rag_llm_services_embeddings.base import EmbeddingProvider


class FakeEmbeddingProvider(EmbeddingProvider):
    """Deterministic, zero-dependency embedding provider producing 1024-dim unit vectors.

    Uses SHA-256 seed to generate reproducible, pseudo-random L2-normalized vectors.
    Permits hermetic offline unit/integration tests without downloading multi-gigabyte models.
    """

    def __init__(
        self,
        dimension: int = 1024,
        model_name: str = "fake-bge-m3-deterministic",
        batch_size: int = 64,
    ) -> None:
        self._dimension = dimension
        self._model_name = model_name
        self._batch_size = batch_size

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dimension(self) -> int:
        return self._dimension

    def _generate_vector(self, text: str) -> list[float]:
        """Generate a deterministic L2-normalized vector for the given string."""
        if not text:
            # Handle empty string with fixed non-zero vector
            vec = [1.0 / math.sqrt(self._dimension)] * self._dimension
            return vec

        digest = hashlib.sha256(text.encode("utf-8")).digest()
        seed_int = int.from_bytes(digest[:8], "big")
        rng = random.Random(seed_int)

        # Generate normally distributed components
        raw = [rng.gauss(0.0, 1.0) for _ in range(self._dimension)]
        sq_sum = sum(x * x for x in raw)
        norm = math.sqrt(sq_sum) if sq_sum > 0 else 1.0

        return [round(x / norm, 6) for x in raw]

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of document texts into deterministic 1024-dim vectors."""
        if not texts:
            return []

        # Yield to event loop to preserve async semantics
        await asyncio.sleep(0)

        results: list[list[float]] = []
        for i in range(0, len(texts), self._batch_size):
            batch = texts[i : i + self._batch_size]
            results.extend([self._generate_vector(t) for t in batch])
        return results

    async def embed_query(self, text: str) -> list[float]:
        """Embed a single query text into a deterministic 1024-dim vector."""
        await asyncio.sleep(0)
        return self._generate_vector(text)
