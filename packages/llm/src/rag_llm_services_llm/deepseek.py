"""DeepSeek provider adapter and deterministic fake provider."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import AsyncIterator, Iterable, Mapping
from typing import Any

import httpx

from rag_llm_services_llm.base import (
    LLMMessage,
    LLMRequest,
    LLMResponse,
    LLMStreamEvent,
    ProviderCapabilities,
)
from rag_llm_services_llm.costs import CostCalculator, TokenPricing
from rag_llm_services_llm.errors import LLMProviderError, map_httpx_error, map_provider_status
from rag_llm_services_llm.usage import LLMUsage, usage_from_payload

logger = logging.getLogger(__name__)

_RESPONSES_UNSUPPORTED_FIELDS = (
    "previous_response_id",
    "conversation",
    "store",
    "truncation",
)


class FakeLLMProvider:
    """Deterministic offline provider used by tests and local development."""

    provider = "fake"

    def __init__(self, answer: str | None = None, model: str = "fake-llm") -> None:
        self._answer = answer or "Mocked answer grounded in [S1]."
        self._model = model

    async def complete(self, request: LLMRequest) -> LLMResponse:
        usage = LLMUsage(
            input_tokens=sum(len(message.content.split()) for message in request.messages),
            output_tokens=len(self._answer.split()),
        )
        usage = LLMUsage(
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cached_input_tokens=0,
            total_tokens=usage.input_tokens + usage.output_tokens,
            estimated_cost_usd=0.0,
        )
        return LLMResponse(
            content=self._answer,
            model=request.model or self._model,
            provider=self.provider,
            usage=usage,
            latency_ms=0.0,
            raw_response_id="fake-response",
            finish_reason="stop",
        )

    async def structured(
        self,
        request: LLMRequest,
        schema: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        del request, schema
        return {"answer": self._answer}

    async def stream(self, request: LLMRequest) -> AsyncIterator[LLMStreamEvent]:
        response = await self.complete(request)
        for token in response.content.split():
            yield LLMStreamEvent(event_type="response.output_text.delta", delta=token + " ")
        yield LLMStreamEvent(
            event_type="response.completed", response=response, usage=response.usage
        )

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            provider=self.provider,
            model=self._model,
            supports_responses=True,
            supports_streaming=True,
            supports_structured_outputs=True,
            supports_tool_calls=False,
            supports_chat_completions_fallback=False,
        )


class DeepSeekProvider:
    """DeepSeek OpenAI-compatible provider using Responses first."""

    provider = "deepseek"

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = "https://api.deepseek.com",
        model: str = "deepseek-v4-flash",
        api_mode: str = "responses",
        timeout_seconds: float = 60.0,
        max_output_tokens: int = 2048,
        max_retries: int = 2,
        retry_backoff_seconds: float = 0.25,
        allow_chat_completions_fallback: bool = False,
        fallback_reason: str | None = None,
        pricing: TokenPricing | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        if self._base_url.endswith("/v1"):
            raise LLMProviderError(
                "DEEPSEEK_BASE_URL must not include the /v1 path suffix",
                code="LLM_CONFIG_INVALID",
                status_code=500,
            )
        self._model = model
        self._api_mode = api_mode
        self._timeout_seconds = timeout_seconds
        self._max_output_tokens = max_output_tokens
        self._max_retries = max_retries
        self._retry_backoff_seconds = retry_backoff_seconds
        self._allow_chat_completions_fallback = allow_chat_completions_fallback
        self._fallback_reason = fallback_reason
        self._costs = CostCalculator(pricing or TokenPricing())
        self._client = http_client or httpx.AsyncClient(
            base_url=self._base_url,
            timeout=httpx.Timeout(timeout_seconds),
        )

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            provider=self.provider,
            model=self._model,
            supports_responses=True,
            supports_streaming=True,
            supports_structured_outputs=True,
            supports_tool_calls=False,
            supports_chat_completions_fallback=self._allow_chat_completions_fallback,
            unsupported_fields=_RESPONSES_UNSUPPORTED_FIELDS,
        )

    async def complete(self, request: LLMRequest) -> LLMResponse:
        if self._api_mode == "responses":
            return await self._complete_responses(request)
        if self._api_mode == "chat_completions":
            return await self._complete_chat_completions(request)
        raise LLMProviderError(
            "Unsupported DeepSeek API mode",
            code="LLM_CONFIG_INVALID",
            status_code=500,
        )

    async def structured(
        self,
        request: LLMRequest,
        schema: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        structured_request = LLMRequest(
            messages=request.messages,
            model=request.model,
            max_output_tokens=request.max_output_tokens,
            temperature=request.temperature,
            response_format={"type": "json_object", "schema": dict(schema)},
            idempotency_key=request.idempotency_key,
        )
        response = await self.complete(structured_request)
        try:
            parsed = json.loads(response.content)
        except json.JSONDecodeError as exc:
            raise LLMProviderError(
                "LLM provider returned malformed structured output",
                code="LLM_MALFORMED_STRUCTURED_OUTPUT",
                status_code=502,
            ) from exc
        if not isinstance(parsed, dict):
            raise LLMProviderError(
                "LLM provider returned non-object structured output",
                code="LLM_MALFORMED_STRUCTURED_OUTPUT",
                status_code=502,
            )
        return parsed

    async def stream(self, request: LLMRequest) -> AsyncIterator[LLMStreamEvent]:
        if self._api_mode != "responses":
            raise LLMProviderError(
                "Streaming is only supported through Responses API mode",
                code="LLM_CONFIG_INVALID",
                status_code=500,
            )

        payload = self._responses_payload(request, stream=True)
        headers = self._headers(request)
        start = time.perf_counter()
        try:
            async with self._client.stream(
                "POST", "/responses", json=payload, headers=headers
            ) as response:
                if response.status_code >= 400:
                    raise map_provider_status(response.status_code)
                async for event in parse_responses_sse(response.aiter_lines()):
                    if event.response is not None and event.response.latency_ms == 0.0:
                        elapsed = round((time.perf_counter() - start) * 1000.0, 2)
                        event = LLMStreamEvent(
                            event_type=event.event_type,
                            delta=event.delta,
                            response=LLMResponse(
                                content=event.response.content,
                                model=event.response.model,
                                provider=event.response.provider,
                                usage=event.response.usage,
                                latency_ms=elapsed,
                                retry_count=event.response.retry_count,
                                raw_response_id=event.response.raw_response_id,
                                finish_reason=event.response.finish_reason,
                            ),
                            usage=event.usage,
                            error_code=event.error_code,
                            error_message=event.error_message,
                        )
                    yield event
        except httpx.HTTPError as exc:
            raise map_httpx_error(exc) from exc

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _complete_responses(self, request: LLMRequest) -> LLMResponse:
        start = time.perf_counter()
        retry_count, payload = await self._post_json(
            "/responses", self._responses_payload(request), request
        )
        usage = self._costs.estimate(usage_from_payload(payload))
        return LLMResponse(
            content=extract_responses_text(payload),
            model=str(payload.get("model") or request.model or self._model),
            provider=self.provider,
            usage=usage,
            latency_ms=round((time.perf_counter() - start) * 1000.0, 2),
            retry_count=retry_count,
            raw_response_id=str(payload.get("id")) if payload.get("id") is not None else None,
            finish_reason=str(payload.get("status")) if payload.get("status") is not None else None,
        )

    async def _complete_chat_completions(self, request: LLMRequest) -> LLMResponse:
        if not self._allow_chat_completions_fallback or not self._fallback_reason:
            raise LLMProviderError(
                "Chat Completions fallback requires an explicit fallback_reason",
                code="LLM_FALLBACK_REASON_REQUIRED",
                status_code=500,
            )
        logger.info(
            "Using DeepSeek Chat Completions fallback",
            extra={"fallback_reason": self._fallback_reason},
        )
        start = time.perf_counter()
        retry_count, payload = await self._post_json(
            "/chat/completions",
            self._chat_payload(request),
            request,
        )
        usage = self._costs.estimate(usage_from_payload(payload))
        return LLMResponse(
            content=extract_chat_text(payload),
            model=str(payload.get("model") or request.model or self._model),
            provider=self.provider,
            usage=usage,
            latency_ms=round((time.perf_counter() - start) * 1000.0, 2),
            retry_count=retry_count,
            raw_response_id=str(payload.get("id")) if payload.get("id") is not None else None,
            finish_reason=_extract_chat_finish_reason(payload),
        )

    async def _post_json(
        self,
        path: str,
        payload: dict[str, Any],
        request: LLMRequest,
    ) -> tuple[int, dict[str, Any]]:
        attempts = self._max_retries + 1 if request.idempotency_key else 1
        last_error: LLMProviderError | None = None
        for attempt in range(attempts):
            try:
                response = await self._client.post(
                    path, json=payload, headers=self._headers(request)
                )
                if response.status_code >= 400:
                    mapped = map_provider_status(response.status_code)
                    if mapped.retryable and attempt + 1 < attempts:
                        last_error = mapped
                        await asyncio.sleep(self._retry_backoff_seconds * (2**attempt))
                        continue
                    raise mapped
                decoded = response.json()
                if not isinstance(decoded, dict):
                    raise LLMProviderError(
                        "LLM provider returned malformed JSON",
                        code="LLM_MALFORMED_RESPONSE",
                        status_code=502,
                    )
                return attempt, decoded
            except httpx.HTTPError as exc:
                mapped = map_httpx_error(exc)
                if mapped.retryable and attempt + 1 < attempts:
                    last_error = mapped
                    await asyncio.sleep(self._retry_backoff_seconds * (2**attempt))
                    continue
                raise mapped from exc
        assert last_error is not None
        raise last_error

    def _headers(self, request: LLMRequest) -> dict[str, str]:
        headers = {"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"}
        if request.idempotency_key:
            headers["Idempotency-Key"] = request.idempotency_key
        return headers

    def _responses_payload(self, request: LLMRequest, *, stream: bool = False) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": request.model or self._model,
            "input": [_message_to_payload(message) for message in request.messages],
            "max_output_tokens": request.max_output_tokens or self._max_output_tokens,
            "stream": stream,
        }
        if request.temperature is not None:
            payload["temperature"] = request.temperature
        if request.response_format is not None:
            payload["text"] = {"format": dict(request.response_format)}
        return payload

    def _chat_payload(self, request: LLMRequest) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": request.model or self._model,
            "messages": [_message_to_payload(message) for message in request.messages],
            "max_tokens": request.max_output_tokens or self._max_output_tokens,
            "stream": False,
        }
        if request.temperature is not None:
            payload["temperature"] = request.temperature
        if request.response_format is not None:
            payload["response_format"] = dict(request.response_format)
        return payload


def _message_to_payload(message: LLMMessage) -> dict[str, str]:
    return {"role": message.role.value, "content": message.content}


def extract_responses_text(payload: Mapping[str, Any]) -> str:
    """Extract assistant text from a Responses API payload."""
    output_text = payload.get("output_text")
    if isinstance(output_text, str):
        return output_text
    parts: list[str] = []
    output = payload.get("output", [])
    if isinstance(output, list):
        for item in output:
            if not isinstance(item, dict):
                continue
            content = item.get("content", [])
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict):
                        text = block.get("text")
                        if isinstance(text, str):
                            parts.append(text)
    return "".join(parts)


def extract_chat_text(payload: Mapping[str, Any]) -> str:
    """Extract assistant text from a Chat Completions payload."""
    choices = payload.get("choices", [])
    if not isinstance(choices, list) or not choices:
        return ""
    first = choices[0]
    if not isinstance(first, dict):
        return ""
    message = first.get("message", {})
    if isinstance(message, dict) and isinstance(message.get("content"), str):
        return str(message["content"])
    return ""


def _extract_chat_finish_reason(payload: Mapping[str, Any]) -> str | None:
    choices = payload.get("choices", [])
    if isinstance(choices, list) and choices and isinstance(choices[0], dict):
        finish_reason = choices[0].get("finish_reason")
        return str(finish_reason) if finish_reason is not None else None
    return None


async def parse_responses_sse(lines: AsyncIterator[str]) -> AsyncIterator[LLMStreamEvent]:
    """Parse semantic Responses SSE events.

    Responses streams end with `response.completed`, `response.incomplete`, or
    `response.failed`. A Chat Completions `[DONE]` sentinel is ignored instead
    of treated as a terminal condition.
    """
    event_type: str | None = None
    data_lines: list[str] = []
    async for line in lines:
        if line == "":
            if event_type or data_lines:
                parsed = _parse_responses_event(event_type, data_lines)
                if parsed is not None:
                    yield parsed
            event_type = None
            data_lines = []
            continue
        if line.startswith("event:"):
            event_type = line.removeprefix("event:").strip()
        elif line.startswith("data:"):
            data = line.removeprefix("data:").strip()
            if data != "[DONE]":
                data_lines.append(data)
    if event_type or data_lines:
        parsed = _parse_responses_event(event_type, data_lines)
        if parsed is not None:
            yield parsed


def _parse_responses_event(
    event_type: str | None, data_lines: Iterable[str]
) -> LLMStreamEvent | None:
    raw_data = "\n".join(data_lines)
    if not raw_data:
        return LLMStreamEvent(event_type=event_type or "message")
    try:
        payload = json.loads(raw_data)
    except json.JSONDecodeError:
        return LLMStreamEvent(event_type=event_type or "message", delta=raw_data)
    if not isinstance(payload, dict):
        return None

    resolved_event_type = event_type or str(payload.get("type") or "message")
    if resolved_event_type.endswith(".delta"):
        delta = payload.get("delta", payload.get("text", ""))
        return LLMStreamEvent(event_type=resolved_event_type, delta=str(delta or ""))
    if resolved_event_type == "response.completed":
        response_payload = payload.get("response", payload)
        if isinstance(response_payload, dict):
            usage = usage_from_payload(response_payload)
            return LLMStreamEvent(
                event_type=resolved_event_type,
                response=LLMResponse(
                    content=extract_responses_text(response_payload),
                    model=str(response_payload.get("model") or ""),
                    provider="deepseek",
                    usage=usage,
                    latency_ms=0.0,
                    raw_response_id=str(response_payload.get("id"))
                    if response_payload.get("id") is not None
                    else None,
                    finish_reason=str(response_payload.get("status") or "completed"),
                ),
                usage=usage,
            )
    if resolved_event_type in {"response.incomplete", "response.failed"}:
        response_payload = payload.get("response", payload)
        error_payload = (
            response_payload.get("error", {}) if isinstance(response_payload, dict) else {}
        )
        if not isinstance(error_payload, dict):
            error_payload = {}
        return LLMStreamEvent(
            event_type=resolved_event_type,
            error_code=str(error_payload.get("code") or resolved_event_type),
            error_message=str(
                error_payload.get("message") or "LLM provider stream did not complete"
            ),
        )
    return LLMStreamEvent(event_type=resolved_event_type, delta=str(payload.get("delta") or ""))
