"""Reranker provider interface and implementations for cross-encoder reranking."""

from __future__ import annotations

import asyncio
import logging
import re
import threading
from collections.abc import Callable
from typing import Any, Protocol, runtime_checkable

from rag_llm_services_rag.retrieval.types import RetrievalResult
from rag_llm_services_shared.errors import UpstreamUnavailableError

logger = logging.getLogger(__name__)
_WORD_RE = re.compile(r"\w+")


@runtime_checkable
class RerankerProvider(Protocol):
    """Protocol for neural or lexical cross-encoder reranking."""

    @property
    def model_name(self) -> str:
        """Model identifier (e.g. 'BAAI/bge-reranker-v2-m3', 'fake-reranker')."""
        ...

    async def rerank(
        self,
        query: str,
        candidates: list[RetrievalResult],
        top_k: int | None = None,
    ) -> list[RetrievalResult]:
        """Score and reorder chunk candidates relative to the query."""
        ...


class NullRerankerProvider(RerankerProvider):
    """Pass-through reranker used when reranking is disabled in configuration."""

    def __init__(self, model_name: str = "none") -> None:
        self._model_name = model_name

    @property
    def model_name(self) -> str:
        return self._model_name

    async def rerank(
        self,
        query: str,
        candidates: list[RetrievalResult],
        top_k: int | None = None,
    ) -> list[RetrievalResult]:
        if top_k is not None and top_k > 0:
            return candidates[:top_k]
        return list(candidates)


class FakeRerankerProvider(RerankerProvider):
    """Deterministic, test-friendly reranker provider.

    Computes deterministic scores based on query term frequency and token matches,
    with an optional custom scorer hook for specific unit test assertions.
    """

    def __init__(
        self,
        model_name: str = "fake-reranker",
        custom_scorer: Callable[[str, RetrievalResult], float] | None = None,
    ) -> None:
        self._model_name = model_name
        self._custom_scorer = custom_scorer

    @property
    def model_name(self) -> str:
        return self._model_name

    def _default_score(self, query: str, candidate: RetrievalResult) -> float:
        """Compute deterministic score based on lexical term overlap and content hash."""
        query_words = set(_WORD_RE.findall(query.lower()))
        if not query_words:
            return 0.5

        content_lower = candidate.content.lower()
        matched = sum(1 for word in query_words if word in content_lower)
        overlap_ratio = matched / len(query_words)

        # Deterministic micro-tie-breaker derived from chunk ID to prevent identical scores
        hash_offset = (hash(str(candidate.chunk_id)) % 1000) / 10000.0
        return round(overlap_ratio * 0.9 + hash_offset, 6)

    async def rerank(
        self,
        query: str,
        candidates: list[RetrievalResult],
        top_k: int | None = None,
    ) -> list[RetrievalResult]:
        if not candidates:
            return []

        scored_list: list[tuple[float, RetrievalResult]] = []
        for c in candidates:
            if self._custom_scorer is not None:
                score = self._custom_scorer(query, c)
            else:
                score = self._default_score(query, c)
            scored_list.append((score, c))

        # Sort descending by rerank score; tie-break by chunk ID string
        scored_list.sort(key=lambda item: (-item[0], str(item[1].chunk_id)))

        if top_k is not None and top_k > 0:
            scored_list = scored_list[:top_k]

        reranked: list[RetrievalResult] = []
        for rank, (score, orig) in enumerate(scored_list, start=1):
            res = RetrievalResult(
                chunk_id=orig.chunk_id,
                document_id=orig.document_id,
                content=orig.content,
                score=score,
                retrieval_method=orig.retrieval_method,
                filename=orig.filename,
                page=orig.page,
                section=orig.section,
                chunk_index=orig.chunk_index,
                token_count=orig.token_count,
                rank=rank,
                metadata=dict(orig.metadata),
            )
            reranked.append(res)

        return reranked


class BGERerankerProvider(RerankerProvider):
    """Process-scoped BGE cross-encoder reranker provider.

    Offloads CPU/CUDA inference from the asyncio event loop via `asyncio.to_thread`.
    """

    _lock = threading.Lock()
    _shared_model: Any = None
    _shared_model_key: tuple[str, str] | None = None

    def __init__(
        self,
        model_name: str = "BAAI/bge-reranker-v2-m3",
        device: str = "cpu",
        batch_size: int = 32,
        max_length: int = 512,
        model_runner: Callable[[list[tuple[str, str]]], list[float]] | None = None,
    ) -> None:
        self._model_name = model_name
        self._device = device
        self._batch_size = batch_size
        self._max_length = max_length
        self._model_runner = model_runner

    @property
    def model_name(self) -> str:
        return self._model_name

    def _get_or_load_model(self) -> Any:
        if self._model_runner is not None:
            return self._model_runner

        cache_key = (self._model_name, self._device)
        with self._lock:
            if (
                BGERerankerProvider._shared_model is not None
                and BGERerankerProvider._shared_model_key == cache_key
            ):
                return BGERerankerProvider._shared_model

            logger.info(
                "Loading BGE reranker '%s' on device '%s'",
                self._model_name,
                self._device,
            )

            # 1. Try FlagEmbedding FlagReranker
            try:
                from FlagEmbedding import FlagReranker  # type: ignore[import-not-found]

                model = FlagReranker(
                    self._model_name,
                    use_fp16=(self._device == "cuda"),
                    device=self._device,
                )
                BGERerankerProvider._shared_model = model
                BGERerankerProvider._shared_model_key = cache_key
                return model
            except ImportError:
                pass

            # 2. Try sentence_transformers CrossEncoder
            try:
                from sentence_transformers import CrossEncoder  # type: ignore[import-not-found]

                model = CrossEncoder(
                    self._model_name,
                    max_length=self._max_length,
                    device=self._device,
                )
                BGERerankerProvider._shared_model = model
                BGERerankerProvider._shared_model_key = cache_key
                return model
            except ImportError:
                pass

            raise UpstreamUnavailableError(
                "BGE reranker model dependencies not installed. "
                "Install 'FlagEmbedding' or 'sentence-transformers' with PyTorch, "
                "or configure RERANKER_PROVIDER=fake or RERANKER_PROVIDER=none for test/offline environments."
            )

    def _sync_rerank(
        self,
        query: str,
        candidates: list[RetrievalResult],
    ) -> list[float]:
        if not candidates:
            return []

        model = self._get_or_load_model()
        pairs = [(query, c.content) for c in candidates]

        if callable(model) and not hasattr(model, "compute_score"):
            return model(pairs)

        if hasattr(model, "compute_score"):
            scores = model.compute_score(pairs, max_length=self._max_length)
            if isinstance(scores, (int, float)):
                return [float(scores)]
            return [float(s) for s in scores]

        if hasattr(model, "predict"):
            scores = model.predict(pairs, batch_size=self._batch_size)
            if isinstance(scores, (int, float)):
                return [float(scores)]
            return [float(s) for s in scores]

        raise UpstreamUnavailableError("Unsupported reranker model runner interface")

    async def rerank(
        self,
        query: str,
        candidates: list[RetrievalResult],
        top_k: int | None = None,
    ) -> list[RetrievalResult]:
        if not candidates:
            return []

        scores = await asyncio.to_thread(self._sync_rerank, query, candidates)

        paired = list(zip(scores, candidates, strict=False))
        paired.sort(key=lambda item: (-item[0], str(item[1].chunk_id)))

        if top_k is not None and top_k > 0:
            paired = paired[:top_k]

        results: list[RetrievalResult] = []
        for rank, (score, orig) in enumerate(paired, start=1):
            res = RetrievalResult(
                chunk_id=orig.chunk_id,
                document_id=orig.document_id,
                content=orig.content,
                score=round(score, 6),
                retrieval_method=orig.retrieval_method,
                filename=orig.filename,
                page=orig.page,
                section=orig.section,
                chunk_index=orig.chunk_index,
                token_count=orig.token_count,
                rank=rank,
                metadata=dict(orig.metadata),
            )
            results.append(res)

        return results
