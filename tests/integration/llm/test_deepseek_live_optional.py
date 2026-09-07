"""Optional DeepSeek live smoke test.

The shared test fixture scrubs app environment variables during test execution,
so opt-in values are captured at import time before the fixture runs. This test
is skipped by default and never consumes paid provider calls unless explicitly
enabled by the operator.
"""

from __future__ import annotations

import os

import pytest

from rag_llm_services_llm.base import LLMMessage, LLMRequest, MessageRole
from rag_llm_services_llm.deepseek import DeepSeekProvider

_RUN_LIVE = os.getenv("RUN_DEEPSEEK_LIVE_TESTS", "").lower() in {"1", "true", "yes"}
_API_KEY = os.getenv("DEEPSEEK_API_KEY")


@pytest.mark.skipif(
    not (_RUN_LIVE and _API_KEY),
    reason="DeepSeek live smoke requires RUN_DEEPSEEK_LIVE_TESTS=1 and DEEPSEEK_API_KEY",
)
@pytest.mark.asyncio
async def test_deepseek_live_responses_smoke() -> None:
    assert _API_KEY is not None
    provider = DeepSeekProvider(api_key=_API_KEY, max_retries=0, max_output_tokens=16)
    try:
        response = await provider.complete(
            LLMRequest(
                messages=(
                    LLMMessage(
                        role=MessageRole.USER,
                        content="Reply with exactly: live smoke ok",
                    ),
                )
            )
        )
    finally:
        await provider.aclose()

    assert response.content
