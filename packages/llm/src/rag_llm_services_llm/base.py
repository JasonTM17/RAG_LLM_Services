"""Provider-neutral LLM gateway types."""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol

from rag_llm_services_llm.usage import LLMUsage


class MessageRole(StrEnum):
    """Roles accepted by the internal gateway."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


@dataclass(frozen=True)
class LLMMessage:
    """One message passed to an LLM provider."""

    role: MessageRole
    content: str


@dataclass(frozen=True)
class LLMRequest:
    """Provider-neutral completion request."""

    messages: tuple[LLMMessage, ...]
    model: str | None = None
    max_output_tokens: int | None = None
    temperature: float | None = None
    response_format: Mapping[str, Any] | None = None
    idempotency_key: str | None = None


@dataclass(frozen=True)
class LLMResponse:
    """Provider-neutral completion response."""

    content: str
    model: str
    provider: str
    usage: LLMUsage
    latency_ms: float
    retry_count: int = 0
    raw_response_id: str | None = None
    finish_reason: str | None = None


@dataclass(frozen=True)
class LLMStructuredResponse:
    """Provider-neutral structured output with usage metadata."""

    output: Mapping[str, Any]
    model: str
    provider: str
    usage: LLMUsage
    latency_ms: float
    retry_count: int = 0
    raw_response_id: str | None = None
    finish_reason: str | None = None


@dataclass(frozen=True)
class LLMStreamEvent:
    """One provider streaming event normalized enough for API SSE output."""

    event_type: str
    delta: str = ""
    response: LLMResponse | None = None
    usage: LLMUsage | None = None
    error_code: str | None = None
    error_message: str | None = None


@dataclass(frozen=True)
class ProviderCapabilities:
    """Static provider capability matrix used by services and tests."""

    provider: str
    model: str
    supports_responses: bool
    supports_streaming: bool
    supports_structured_outputs: bool
    supports_tool_calls: bool
    supports_chat_completions_fallback: bool
    unsupported_fields: tuple[str, ...] = field(default_factory=tuple)


class LLMProvider(Protocol):
    """Async provider interface consumed by application services."""

    async def complete(self, request: LLMRequest) -> LLMResponse:
        """Return one completed assistant response."""
        ...

    def stream(self, request: LLMRequest) -> AsyncIterator[LLMStreamEvent]:
        """Stream provider events without using Chat Completions `[DONE]` as a sentinel."""
        ...

    async def structured(
        self,
        request: LLMRequest,
        schema: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        """Return parsed structured output."""
        ...

    async def structured_response(
        self,
        request: LLMRequest,
        schema: Mapping[str, Any],
    ) -> LLMStructuredResponse:
        """Return parsed structured output with provider usage metadata."""
        ...

    def capabilities(self) -> ProviderCapabilities:
        """Return provider capability metadata."""
        ...
