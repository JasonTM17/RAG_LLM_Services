"""DeepSeek provider configuration and request-shape tests."""

from __future__ import annotations

import json

import httpx
import pytest
from pydantic import ValidationError

from rag_llm_services_api.core.config import Settings
from rag_llm_services_api.infrastructure.llm import build_llm_provider
from rag_llm_services_llm.base import LLMMessage, LLMRequest, MessageRole
from rag_llm_services_llm.costs import TokenPricing
from rag_llm_services_llm.deepseek import DeepSeekProvider, FakeLLMProvider


def test_default_llm_provider_is_fake_while_deepseek_defaults_are_pinned() -> None:
    settings = Settings(_env_file=None)

    assert settings.llm.provider == "fake"
    assert settings.deepseek.base_url == "https://api.deepseek.com"
    assert settings.deepseek.model == "deepseek-v4-flash"
    assert settings.deepseek.api_mode == "responses"
    assert settings.deepseek.allow_chat_completions_fallback is False


def test_provider_factory_uses_fake_for_offline_default() -> None:
    assert isinstance(build_llm_provider(Settings(_env_file=None)), FakeLLMProvider)


def test_chat_completions_fallback_requires_configured_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DEEPSEEK_API_MODE", "chat_completions")
    monkeypatch.setenv("DEEPSEEK_ALLOW_CHAT_COMPLETIONS_FALLBACK", "true")
    with pytest.raises(ValidationError, match="DEEPSEEK_FALLBACK_REASON"):
        Settings(_env_file=None)

    monkeypatch.setenv("DEEPSEEK_FALLBACK_REASON", "responses compatibility probe failed")
    settings = Settings(_env_file=None)
    assert settings.deepseek.fallback_reason == "responses compatibility probe failed"


def test_deepseek_capabilities_pin_responses_first_contract() -> None:
    provider = DeepSeekProvider(api_key="test-key")

    capabilities = provider.capabilities()

    assert capabilities.provider == "deepseek"
    assert capabilities.model == "deepseek-v4-flash"
    assert capabilities.supports_responses is True
    assert capabilities.supports_streaming is True
    assert capabilities.supports_structured_outputs is True
    assert capabilities.supports_tool_calls is False
    assert "previous_response_id" in capabilities.unsupported_fields
    assert "conversation" in capabilities.unsupported_fields


@pytest.mark.asyncio
async def test_deepseek_responses_complete_posts_to_responses_without_v1() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.url == "https://api.deepseek.com/responses"
        payload = json.loads(request.content.decode("utf-8"))
        assert payload["model"] == "deepseek-v4-flash"
        assert payload["input"][0] == {"role": "user", "content": "hello"}
        assert payload["stream"] is False
        assert request.headers["Idempotency-Key"] == "msg-1"
        return httpx.Response(
            200,
            json={
                "id": "resp_1",
                "model": "deepseek-v4-flash",
                "status": "completed",
                "output": [
                    {
                        "type": "message",
                        "content": [{"type": "output_text", "text": "Answer [S1]."}],
                    }
                ],
                "usage": {
                    "input_tokens": 100,
                    "input_tokens_details": {"cached_tokens": 25},
                    "output_tokens": 20,
                    "total_tokens": 120,
                },
            },
        )

    client = httpx.AsyncClient(
        base_url="https://api.deepseek.com",
        transport=httpx.MockTransport(handler),
    )
    provider = DeepSeekProvider(
        api_key="test-key",
        http_client=client,
        retry_backoff_seconds=0.0,
        pricing=TokenPricing(
            input_cache_miss_usd_per_1m=1.0,
            input_cache_hit_usd_per_1m=0.5,
            output_usd_per_1m=2.0,
        ),
    )

    response = await provider.complete(
        LLMRequest(
            messages=(LLMMessage(role=MessageRole.USER, content="hello"),),
            idempotency_key="msg-1",
        )
    )

    assert response.content == "Answer [S1]."
    assert response.usage.input_tokens == 100
    assert response.usage.cached_input_tokens == 25
    assert response.usage.output_tokens == 20
    assert response.usage.estimated_cost_usd == 0.0001275
    assert len(requests) == 1
    await client.aclose()
