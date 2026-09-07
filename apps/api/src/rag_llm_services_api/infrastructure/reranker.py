"""Reranker provider factory and lifecycle management."""

from __future__ import annotations

from functools import lru_cache

from rag_llm_services_api.core.config import Settings, get_settings
from rag_llm_services_rag.retrieval.reranker import (
    BGERerankerProvider,
    FakeRerankerProvider,
    NullRerankerProvider,
    RerankerProvider,
)


@lru_cache
def _get_cached_reranker_provider(
    provider_name: str, model_name: str, app_env: str
) -> RerankerProvider:
    if provider_name in ("none", "disabled", "null", "false"):
        return NullRerankerProvider()

    if provider_name == "fake" or app_env == "test":
        return FakeRerankerProvider(model_name=model_name)

    return BGERerankerProvider(
        model_name=model_name,
        device="cpu",
    )


def get_reranker_provider(settings: Settings | None = None) -> RerankerProvider:
    """Return configured reranker provider singleton.

    Uses FakeRerankerProvider when RERANKER_PROVIDER=fake or APP_ENV=test.
    Uses NullRerankerProvider when RERANKER_PROVIDER is 'none' or 'disabled'.
    Otherwise uses process-scoped BGERerankerProvider.
    """
    cfg = settings or get_settings()
    provider_name = cfg.embedding.reranker_provider.lower().strip()
    return _get_cached_reranker_provider(provider_name, cfg.embedding.reranker_model, cfg.app.env)
