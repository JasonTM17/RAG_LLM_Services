"""Embedding provider factory and lifecycle management."""

from __future__ import annotations

from functools import lru_cache

from rag_llm_services_api.core.config import Settings, get_settings
from rag_llm_services_embeddings.base import EmbeddingProvider
from rag_llm_services_embeddings.bge_m3 import BGEM3EmbeddingProvider
from rag_llm_services_embeddings.fake import FakeEmbeddingProvider


@lru_cache
def get_embedding_provider(settings: Settings | None = None) -> EmbeddingProvider:
    """Return configured embedding provider singleton.

    Uses FakeEmbeddingProvider when EMBEDDING_PROVIDER=fake or APP_ENV=test.
    Otherwise uses process-scoped BGEM3EmbeddingProvider.
    """
    cfg = settings or get_settings()
    provider_name = cfg.embedding.provider.lower().strip()

    if provider_name == "fake" or cfg.app.env == "test":
        return FakeEmbeddingProvider(
            dimension=1024,
            model_name=cfg.embedding.model,
        )

    return BGEM3EmbeddingProvider(
        model_name=cfg.embedding.model,
        device="cpu",
    )
