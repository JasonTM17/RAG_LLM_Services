"""BGE-M3 dense embedding provider with process-scoped lifecycle and batching."""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from collections.abc import Callable
from typing import Any

from rag_llm_services_embeddings.base import EmbeddingProvider
from rag_llm_services_shared.errors import UpstreamUnavailableError

logger = logging.getLogger(__name__)


class BGEM3EmbeddingProvider(EmbeddingProvider):
    """Process-scoped BGE-M3 embedding provider generating 1024-dim dense vectors.

    Supports CPU and CUDA execution, batching, and offloading CPU-intensive inference
    outside the asyncio event loop via `asyncio.to_thread`.
    """

    _lock = threading.Lock()
    _shared_model: Any = None
    _shared_model_name: str | None = None

    def __init__(
        self,
        model_name: str = "BAAI/bge-m3",
        device: str = "cpu",
        batch_size: int = 32,
        max_length: int = 8192,
        normalize_embeddings: bool = True,
        model_runner: Callable[[list[str]], list[list[float]]] | None = None,
    ) -> None:
        self._model_name = model_name
        self._device = device
        self._batch_size = batch_size
        self._max_length = max_length
        self._normalize_embeddings = normalize_embeddings
        self._model_runner = model_runner
        self._dimension = 1024

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dimension(self) -> int:
        return self._dimension

    @property
    def device(self) -> str:
        return self._device

    @property
    def batch_size(self) -> int:
        return self._batch_size

    def _get_or_load_model(self) -> Any:
        """Load the model once at process scope, reusing across requests/jobs."""
        if self._model_runner is not None:
            return self._model_runner

        with self._lock:
            if (
                BGEM3EmbeddingProvider._shared_model is not None
                and BGEM3EmbeddingProvider._shared_model_name == self._model_name
            ):
                return BGEM3EmbeddingProvider._shared_model

            logger.info(
                "Loading BGE-M3 model '%s' on device '%s' (process-scoped lifecycle)",
                self._model_name,
                self._device,
            )

            # 1. Try FlagEmbedding (canonical BGE-M3 package)
            try:
                from FlagEmbedding import BGEM3FlagModel  # type: ignore[import-not-found]

                model = BGEM3FlagModel(
                    self._model_name,
                    use_fp16=(self._device == "cuda"),
                    device=self._device,
                )
                BGEM3EmbeddingProvider._shared_model = model
                BGEM3EmbeddingProvider._shared_model_name = self._model_name
                return model
            except ImportError:
                pass

            # 2. Try sentence-transformers
            try:
                from sentence_transformers import (
                    SentenceTransformer,  # type: ignore[import-not-found]
                )

                model = SentenceTransformer(self._model_name, device=self._device)
                BGEM3EmbeddingProvider._shared_model = model
                BGEM3EmbeddingProvider._shared_model_name = self._model_name
                return model
            except ImportError:
                pass

            raise UpstreamUnavailableError(
                "BGE-M3 embedding model dependencies not installed. "
                "Install 'FlagEmbedding' or 'sentence-transformers' with PyTorch for live inference, "
                "or configure EMBEDDING_PROVIDER=fake for test/offline environments."
            )

    def _sync_embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Synchronous CPU/CUDA inference for a single batch."""
        if not texts:
            return []

        model = self._get_or_load_model()

        # If custom model runner was provided (e.g. for testing)
        if callable(model) and not hasattr(model, "encode"):
            return model(texts)

        # FlagEmbedding BGEM3FlagModel returns a dict with 'dense_vecs'
        if hasattr(model, "encode") and hasattr(model, "encode_dense"):
            output = model.encode(
                texts,
                batch_size=len(texts),
                max_length=self._max_length,
                return_dense=True,
                return_sparse=False,
                return_colbert_vecs=False,
            )
            dense = output["dense_vecs"]
            return dense.tolist() if hasattr(dense, "tolist") else [list(v) for v in dense]

        # SentenceTransformer returns numpy ndarray
        if hasattr(model, "encode"):
            output = model.encode(
                texts,
                batch_size=len(texts),
                normalize_embeddings=self._normalize_embeddings,
                show_progress_bar=False,
            )
            return output.tolist() if hasattr(output, "tolist") else [list(v) for v in output]

        raise UpstreamUnavailableError("Unsupported embedding model runner interface")

    def _sync_embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Process all texts in batches with latency logging."""
        start_time = time.perf_counter()
        results: list[list[float]] = []

        for i in range(0, len(texts), self._batch_size):
            batch = texts[i : i + self._batch_size]
            batch_vectors = self._sync_embed_batch(batch)
            results.extend(batch_vectors)

        elapsed = time.perf_counter() - start_time
        logger.debug(
            "Embedded %d document chunks in %.3f seconds (batch_size=%d)",
            len(texts),
            elapsed,
            self._batch_size,
        )
        return results

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings asynchronously offloading inference from the event loop."""
        if not texts:
            return []
        return await asyncio.to_thread(self._sync_embed_documents, texts)

    async def embed_query(self, text: str) -> list[float]:
        """Generate embedding for a single query asynchronously."""
        results = await self.embed_documents([text])
        if not results:
            return [0.0] * self._dimension
        return results[0]
