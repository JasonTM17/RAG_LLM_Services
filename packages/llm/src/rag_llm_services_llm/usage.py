"""Token usage extraction for LLM provider responses."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class LLMUsage:
    """Provider-neutral token usage and estimated cost."""

    input_tokens: int = 0
    output_tokens: int = 0
    cached_input_tokens: int = 0
    total_tokens: int = 0
    estimated_cost_usd: float = 0.0


def _int_value(value: object) -> int:
    if isinstance(value, int):
        return max(value, 0)
    if isinstance(value, float):
        return max(int(value), 0)
    return 0


def usage_from_payload(payload: dict[str, Any]) -> LLMUsage:
    """Extract token usage from Responses or Chat Completions payloads."""
    usage = payload.get("usage")
    if not isinstance(usage, dict):
        return LLMUsage()

    input_tokens = _int_value(usage.get("input_tokens", usage.get("prompt_tokens", 0)))
    output_tokens = _int_value(usage.get("output_tokens", usage.get("completion_tokens", 0)))
    total_tokens = _int_value(usage.get("total_tokens", input_tokens + output_tokens))

    input_details = usage.get("input_tokens_details", usage.get("prompt_tokens_details", {}))
    cached_input_tokens = 0
    if isinstance(input_details, dict):
        cached_input_tokens = _int_value(
            input_details.get(
                "cached_tokens",
                input_details.get("prompt_cache_hit_tokens", 0),
            )
        )
    cached_input_tokens = max(cached_input_tokens, _int_value(usage.get("prompt_cache_hit_tokens")))

    return LLMUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cached_input_tokens=min(cached_input_tokens, input_tokens),
        total_tokens=total_tokens,
    )
