"""Estimated LLM cost calculation."""

from __future__ import annotations

from dataclasses import dataclass

from rag_llm_services_llm.usage import LLMUsage


@dataclass(frozen=True)
class TokenPricing:
    """USD pricing per one million tokens."""

    input_cache_miss_usd_per_1m: float = 0.0
    input_cache_hit_usd_per_1m: float = 0.0
    output_usd_per_1m: float = 0.0


class CostCalculator:
    """Estimate cost from provider token usage and configured pricing."""

    def __init__(self, pricing: TokenPricing) -> None:
        self._pricing = pricing

    def estimate(self, usage: LLMUsage) -> LLMUsage:
        """Return usage with an estimated cost attached."""
        cached = min(usage.cached_input_tokens, usage.input_tokens)
        cache_miss = max(usage.input_tokens - cached, 0)
        cost = (
            (cache_miss * self._pricing.input_cache_miss_usd_per_1m)
            + (cached * self._pricing.input_cache_hit_usd_per_1m)
            + (usage.output_tokens * self._pricing.output_usd_per_1m)
        ) / 1_000_000
        return LLMUsage(
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cached_input_tokens=usage.cached_input_tokens,
            total_tokens=usage.total_tokens,
            estimated_cost_usd=round(cost, 8),
        )
