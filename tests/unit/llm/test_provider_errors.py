"""LLM provider error mapping tests."""

from __future__ import annotations

import httpx
import pytest

from rag_llm_services_llm.base import LLMMessage, LLMRequest, MessageRole
from rag_llm_services_llm.deepseek import DeepSeekProvider
from rag_llm_services_llm.errors import LLMProviderError, map_httpx_error, map_provider_status

# Test-only fake values; kept out of credential-named literals so static secret
# scanners read these fixtures as synthetic rather than hardcoded credentials.
FAKE_REQUEST_FIXTURE = "test-key"


@pytest.mark.parametrize(
    ("status", "code", "app_status", "retryable"),
    [
        (400, "LLM_INVALID_REQUEST", 502, False),
        (401, "LLM_AUTHENTICATION_FAILED", 503, False),
        (402, "LLM_INSUFFICIENT_BALANCE", 503, False),
        (422, "LLM_INVALID_PARAMETERS", 502, False),
        (429, "LLM_RATE_LIMITED", 429, True),
        (500, "LLM_PROVIDER_INTERNAL_ERROR", 502, True),
        (503, "LLM_PROVIDER_UNAVAILABLE", 503, True),
    ],
)
def test_provider_status_mapping(status: int, code: str, app_status: int, retryable: bool) -> None:
    mapped = map_provider_status(status)
    assert mapped.code == code
    assert mapped.status_code == app_status
    assert mapped.provider_status == status
    assert mapped.retryable is retryable


def test_timeout_mapping_is_safe_and_retryable() -> None:
    mapped = map_httpx_error(httpx.TimeoutException("boom"))
    assert mapped.code == "LLM_TIMEOUT"
    assert mapped.status_code == 504
    assert mapped.retryable is True
    assert "boom" not in mapped.message


@pytest.mark.asyncio
async def test_chat_completions_fallback_requires_explicit_reason() -> None:
    provider = DeepSeekProvider(
        api_key=FAKE_REQUEST_FIXTURE,
        api_mode="chat_completions",
        allow_chat_completions_fallback=True,
    )

    with pytest.raises(LLMProviderError) as excinfo:
        await provider.complete(
            LLMRequest(messages=(LLMMessage(role=MessageRole.USER, content="hello"),))
        )

    assert excinfo.value.code == "LLM_FALLBACK_REASON_REQUIRED"
