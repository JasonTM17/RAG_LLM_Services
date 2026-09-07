"""LLM provider factory."""

from __future__ import annotations

import inspect
from functools import lru_cache

from rag_llm_services_api.core.config import Settings, get_settings
from rag_llm_services_api.core.errors import ConfigurationError
from rag_llm_services_llm.base import LLMProvider
from rag_llm_services_llm.costs import TokenPricing
from rag_llm_services_llm.deepseek import DeepSeekProvider, FakeLLMProvider


def build_llm_provider(settings: Settings) -> LLMProvider:
    """Build the configured LLM provider without logging secrets."""
    if settings.llm.provider == "fake":
        return FakeLLMProvider(model="fake-llm")
    if settings.llm.provider != "deepseek":
        raise ConfigurationError("Unsupported LLM provider")

    return DeepSeekProvider(
        api_key=settings.deepseek.api_key,
        base_url=settings.deepseek.base_url,
        model=settings.deepseek.model,
        api_mode=settings.deepseek.api_mode,
        timeout_seconds=settings.llm.request_timeout_seconds,
        max_output_tokens=settings.llm.max_output_tokens,
        max_retries=settings.deepseek.max_retries,
        retry_backoff_seconds=settings.deepseek.retry_backoff_seconds,
        allow_chat_completions_fallback=settings.deepseek.allow_chat_completions_fallback,
        fallback_reason=settings.deepseek.fallback_reason,
        pricing=TokenPricing(
            input_cache_miss_usd_per_1m=settings.deepseek.estimated_input_cache_miss_usd_per_1m,
            input_cache_hit_usd_per_1m=settings.deepseek.estimated_input_cache_hit_usd_per_1m,
            output_usd_per_1m=settings.deepseek.estimated_output_usd_per_1m,
        ),
    )


@lru_cache
def get_llm_provider() -> LLMProvider:
    """Cached provider dependency for FastAPI routes."""
    return build_llm_provider(get_settings())


async def dispose_llm_provider() -> None:
    """Close and clear the cached provider if it owns async resources."""
    if get_llm_provider.cache_info().currsize == 0:
        return
    provider = get_llm_provider()
    close = getattr(provider, "aclose", None)
    if close is not None:
        result = close()
        if inspect.isawaitable(result):
            await result
    get_llm_provider.cache_clear()
