"""LLM cost-estimation tests."""

from rag_llm_services_llm.costs import CostCalculator, TokenPricing
from rag_llm_services_llm.usage import LLMUsage


def test_cost_calculator_splits_cache_hit_and_miss_input_tokens() -> None:
    calculator = CostCalculator(
        TokenPricing(
            input_cache_miss_usd_per_1m=1.0,
            input_cache_hit_usd_per_1m=0.25,
            output_usd_per_1m=2.0,
        )
    )

    usage = calculator.estimate(
        LLMUsage(input_tokens=1000, cached_input_tokens=400, output_tokens=250, total_tokens=1250)
    )

    assert usage.estimated_cost_usd == 0.0012
