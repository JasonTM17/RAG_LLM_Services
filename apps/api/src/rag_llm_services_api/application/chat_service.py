"""Chat application service for retrieval-grounded LLM answers."""

from __future__ import annotations

import json
import logging
import time
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from uuid import UUID

from rag_llm_services_agents.citations import (
    CitationValidationError,
    CitationValidator,
)
from rag_llm_services_api.application.retrieval_service import RetrievalService
from rag_llm_services_api.core.errors import NotFoundError, ValidationError
from rag_llm_services_api.db.models.conversation import MessageModel
from rag_llm_services_api.domain.chat import DEFAULT_CHAT_HISTORY_LIMIT, ChatMessageRole
from rag_llm_services_api.infrastructure.repositories.chat import ChatRepository
from rag_llm_services_llm.base import (
    LLMMessage,
    LLMProvider,
    LLMRequest,
    LLMResponse,
    MessageRole,
)
from rag_llm_services_llm.usage import LLMUsage
from rag_llm_services_observability.metrics import record_error, record_llm_request
from rag_llm_services_rag.retrieval.types import CitedChunk, ContextBundle, RetrievalFilter

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """You answer learning questions using only the provided source context.
If the sources do not contain enough evidence, say so briefly.
Cite supporting claims with source IDs like [S1]."""


@dataclass(frozen=True)
class ChatAnswer:
    """Completed chat answer returned by the application service."""

    conversation_id: UUID
    message_id: UUID
    answer: str
    citations: list[CitedChunk]
    retrieved_sources: list[CitedChunk]
    usage: LLMUsage
    provider: str
    model: str
    latency_ms: float
    retry_count: int


@dataclass(frozen=True)
class ChatStreamChunk:
    """One SSE-ready chat stream chunk."""

    event: str
    delta: str = ""
    conversation_id: UUID | None = None
    message_id: UUID | None = None
    usage: LLMUsage | None = None
    citations: list[CitedChunk] = field(default_factory=list)
    retrieved_sources: list[CitedChunk] = field(default_factory=list)
    error_code: str | None = None
    error_message: str | None = None


class CitationPromptBuilder:
    """Build provider messages without leaking private context to logs."""

    def build(
        self,
        *,
        question: str,
        context_bundle: ContextBundle | None,
        history: list[tuple[str, str]],
    ) -> tuple[LLMMessage, ...]:
        history_messages = [
            LLMMessage(role=MessageRole(role), content=content)
            for role, content in history
            if role in {MessageRole.USER.value, MessageRole.ASSISTANT.value}
        ]
        context_text = context_bundle.context_text if context_bundle else ""
        user_content = f"Question:\n{question}\n\nSource context:\n{context_text}".strip()
        return (
            LLMMessage(role=MessageRole.SYSTEM, content=_SYSTEM_PROMPT),
            *history_messages,
            LLMMessage(role=MessageRole.USER, content=user_content),
        )


class ChatApplicationService:
    """Coordinates local memory, retrieval, provider calls, citations, and usage records."""

    def __init__(
        self,
        *,
        chat_repo: ChatRepository,
        retrieval_service: RetrievalService,
        llm_provider: LLMProvider,
        prompt_builder: CitationPromptBuilder | None = None,
        citation_validator: CitationValidator | None = None,
        history_limit: int = DEFAULT_CHAT_HISTORY_LIMIT,
    ) -> None:
        self._chat_repo = chat_repo
        self._retrieval_service = retrieval_service
        self._llm_provider = llm_provider
        self._prompt_builder = prompt_builder or CitationPromptBuilder()
        self._citation_validator = citation_validator or CitationValidator()
        self._history_limit = history_limit

    async def answer(
        self,
        *,
        owner_id: UUID,
        message: str,
        conversation_id: UUID | None = None,
        knowledge_base_id: UUID | None = None,
        max_output_tokens: int | None = None,
        context_token_budget: int | None = None,
    ) -> ChatAnswer:
        """Return one retrieval-grounded answer and persist local chat state."""
        conversation_id = await self._resolve_conversation(
            owner_id=owner_id, conversation_id=conversation_id, first_message=message
        )
        history = await self._history(owner_id=owner_id, conversation_id=conversation_id)
        context_bundle = await self._retrieve_context(
            owner_id=owner_id,
            message=message,
            knowledge_base_id=knowledge_base_id,
            context_token_budget=context_token_budget,
        )
        user_message = await self._chat_repo.add_message(
            owner_id=owner_id,
            conversation_id=conversation_id,
            role=ChatMessageRole.USER.value,
            content=message,
        )
        request = LLMRequest(
            messages=self._prompt_builder.build(
                question=message, context_bundle=context_bundle, history=history
            ),
            max_output_tokens=max_output_tokens,
            idempotency_key=str(user_message.id),
        )
        provider_started = time.perf_counter()
        try:
            llm_response = await self._llm_provider.complete(request)
        except Exception:
            elapsed_ms = round((time.perf_counter() - provider_started) * 1000.0, 2)
            provider = self._provider_name()
            record_llm_request(provider=provider, status="failed", latency_ms=elapsed_ms)
            record_error("llm", "exception")
            logger.exception(
                "LLM request failed",
                extra={
                    "stage": "llm.complete",
                    "dependency": "llm_provider",
                    "provider": provider,
                    "model": self._provider_model(),
                    "status": "failed",
                    "latency_ms": elapsed_ms,
                    "error_code": "LLM_REQUEST_FAILED",
                },
            )
            raise
        record_llm_request(
            provider=llm_response.provider,
            status="succeeded",
            latency_ms=llm_response.latency_ms,
            usage=llm_response.usage,
        )
        logger.info(
            "LLM request completed",
            extra={
                "stage": "llm.complete",
                "dependency": "llm_provider",
                "provider": llm_response.provider,
                "model": llm_response.model,
                "status": "succeeded",
                "latency_ms": llm_response.latency_ms,
            },
        )
        assistant_message = await self._persist_assistant_response(
            owner_id=owner_id,
            conversation_id=conversation_id,
            response=llm_response,
            context_bundle=context_bundle,
        )
        return ChatAnswer(
            conversation_id=conversation_id,
            message_id=assistant_message.id,
            answer=llm_response.content,
            citations=self._cited_chunks_or_raise(llm_response.content, context_bundle),
            retrieved_sources=context_bundle.cited_chunks if context_bundle else [],
            usage=llm_response.usage,
            provider=llm_response.provider,
            model=llm_response.model,
            latency_ms=llm_response.latency_ms,
            retry_count=llm_response.retry_count,
        )

    async def stream_answer(
        self,
        *,
        owner_id: UUID,
        message: str,
        conversation_id: UUID | None = None,
        knowledge_base_id: UUID | None = None,
        max_output_tokens: int | None = None,
        context_token_budget: int | None = None,
    ) -> AsyncIterator[ChatStreamChunk]:
        """Stream one retrieval-grounded answer and persist it when completed."""
        conversation_id = await self._resolve_conversation(
            owner_id=owner_id, conversation_id=conversation_id, first_message=message
        )
        history = await self._history(owner_id=owner_id, conversation_id=conversation_id)
        context_bundle = await self._retrieve_context(
            owner_id=owner_id,
            message=message,
            knowledge_base_id=knowledge_base_id,
            context_token_budget=context_token_budget,
        )
        user_message = await self._chat_repo.add_message(
            owner_id=owner_id,
            conversation_id=conversation_id,
            role=ChatMessageRole.USER.value,
            content=message,
        )
        request = LLMRequest(
            messages=self._prompt_builder.build(
                question=message, context_bundle=context_bundle, history=history
            ),
            max_output_tokens=max_output_tokens,
            idempotency_key=str(user_message.id),
        )
        answer_parts: list[str] = []
        provider_started = time.perf_counter()
        try:
            async for event in self._llm_provider.stream(request):
                if event.delta:
                    answer_parts.append(event.delta)
                    yield ChatStreamChunk(
                        event=event.event_type,
                        delta=event.delta,
                        conversation_id=conversation_id,
                    )
                    continue
                if event.response is not None:
                    response = _response_with_content(event.response, "".join(answer_parts).strip())
                    record_llm_request(
                        provider=response.provider,
                        status="succeeded",
                        latency_ms=response.latency_ms,
                        usage=response.usage,
                    )
                    logger.info(
                        "LLM stream completed",
                        extra={
                            "stage": "llm.stream",
                            "dependency": "llm_provider",
                            "provider": response.provider,
                            "model": response.model,
                            "status": "succeeded",
                            "latency_ms": response.latency_ms,
                        },
                    )
                    assistant_message = await self._persist_assistant_response(
                        owner_id=owner_id,
                        conversation_id=conversation_id,
                        response=response,
                        context_bundle=context_bundle,
                    )
                    yield ChatStreamChunk(
                        event=event.event_type,
                        conversation_id=conversation_id,
                        message_id=assistant_message.id,
                        usage=response.usage,
                        citations=self._cited_chunks_or_raise(response.content, context_bundle),
                        retrieved_sources=context_bundle.cited_chunks if context_bundle else [],
                    )
                    continue
                if event.error_code:
                    elapsed_ms = round((time.perf_counter() - provider_started) * 1000.0, 2)
                    provider = self._provider_name()
                    record_llm_request(provider=provider, status="failed", latency_ms=elapsed_ms)
                    record_error("llm", "upstream_unavailable")
                    logger.warning(
                        "LLM stream failed",
                        extra={
                            "stage": "llm.stream",
                            "dependency": "llm_provider",
                            "provider": provider,
                            "model": self._provider_model(),
                            "status": "failed",
                            "latency_ms": elapsed_ms,
                            "error_code": event.error_code,
                        },
                    )
                yield ChatStreamChunk(
                    event=event.event_type,
                    conversation_id=conversation_id,
                    error_code=event.error_code,
                    error_message=event.error_message,
                )
        except Exception:
            elapsed_ms = round((time.perf_counter() - provider_started) * 1000.0, 2)
            provider = self._provider_name()
            record_llm_request(provider=provider, status="failed", latency_ms=elapsed_ms)
            record_error("llm", "exception")
            logger.exception(
                "LLM stream failed",
                extra={
                    "stage": "llm.stream",
                    "dependency": "llm_provider",
                    "provider": provider,
                    "model": self._provider_model(),
                    "status": "failed",
                    "latency_ms": elapsed_ms,
                    "error_code": "LLM_STREAM_FAILED",
                },
            )
            raise

    def _provider_name(self) -> str:
        return self._llm_provider.capabilities().provider

    def _provider_model(self) -> str:
        return self._llm_provider.capabilities().model

    async def _resolve_conversation(
        self,
        *,
        owner_id: UUID,
        conversation_id: UUID | None,
        first_message: str,
    ) -> UUID:
        if conversation_id is not None:
            conversation = await self._chat_repo.get_conversation(
                owner_id=owner_id, conversation_id=conversation_id
            )
            if conversation is None:
                raise NotFoundError("Conversation not found")
            return conversation.id
        title = first_message.strip().splitlines()[0][:80] or "New conversation"
        conversation = await self._chat_repo.create_conversation(owner_id=owner_id, title=title)
        return conversation.id

    async def _retrieve_context(
        self,
        *,
        owner_id: UUID,
        message: str,
        knowledge_base_id: UUID | None,
        context_token_budget: int | None,
    ) -> ContextBundle | None:
        retrieval = await self._retrieval_service.search(
            owner_id=owner_id,
            query=message,
            filter=RetrievalFilter(knowledge_base_id=knowledge_base_id)
            if knowledge_base_id
            else None,
            context_token_budget=context_token_budget,
            include_context_bundle=True,
        )
        return retrieval.context_bundle

    async def _history(
        self,
        *,
        owner_id: UUID,
        conversation_id: UUID,
    ) -> list[tuple[str, str]]:
        messages = await self._chat_repo.list_recent_messages(
            owner_id=owner_id,
            conversation_id=conversation_id,
            limit=self._history_limit,
        )
        return [
            (message.role, message.content)
            for message in messages
            if message.role in {ChatMessageRole.USER.value, ChatMessageRole.ASSISTANT.value}
        ]

    async def _persist_assistant_response(
        self,
        *,
        owner_id: UUID,
        conversation_id: UUID,
        response: LLMResponse,
        context_bundle: ContextBundle | None,
    ) -> MessageModel:
        self._cited_chunks_or_raise(response.content, context_bundle)
        source_ids = (
            [chunk.source_id for chunk in context_bundle.cited_chunks] if context_bundle else []
        )
        assistant_message = await self._chat_repo.add_message(
            owner_id=owner_id,
            conversation_id=conversation_id,
            role=ChatMessageRole.ASSISTANT.value,
            content=response.content,
            metadata_json={
                "provider": response.provider,
                "model": response.model,
                "source_ids": source_ids,
            },
        )
        await self._chat_repo.record_llm_usage(
            owner_id=owner_id,
            conversation_id=conversation_id,
            message_id=assistant_message.id,
            provider=response.provider,
            model=response.model,
            usage=response.usage,
            latency_ms=response.latency_ms,
            retry_count=response.retry_count,
        )
        return assistant_message

    def _cited_chunks_or_raise(
        self,
        answer: str,
        context_bundle: ContextBundle | None,
    ) -> list[CitedChunk]:
        try:
            return self._citation_validator.cited_chunks(answer, context_bundle)
        except CitationValidationError as exc:
            raise ValidationError(
                "Assistant response contains invalid citations",
                code="INVALID_CITATION",
                status_code=422,
            ) from exc


def _response_with_content(response: LLMResponse, content: str) -> LLMResponse:
    return LLMResponse(
        content=content or response.content,
        model=response.model,
        provider=response.provider,
        usage=response.usage,
        latency_ms=response.latency_ms,
        retry_count=response.retry_count,
        raw_response_id=response.raw_response_id,
        finish_reason=response.finish_reason,
    )


def stream_chunk_to_json(chunk: ChatStreamChunk) -> str:
    """Serialize a chat stream chunk to safe JSON for SSE data."""
    usage = None
    if chunk.usage is not None:
        usage = getattr(chunk.usage, "__dict__", None)
    return json.dumps(
        {
            "event": chunk.event,
            "delta": chunk.delta,
            "conversation_id": str(chunk.conversation_id) if chunk.conversation_id else None,
            "message_id": str(chunk.message_id) if chunk.message_id else None,
            "usage": usage,
            "citations": [_cited_chunk_to_json(cited) for cited in chunk.citations],
            "retrieved_sources": [_cited_chunk_to_json(cited) for cited in chunk.retrieved_sources],
            "error_code": chunk.error_code,
            "error_message": chunk.error_message,
        },
        ensure_ascii=False,
    )


def new_message_idempotency_key() -> str:
    """Generate a stable idempotency key when a caller needs one before persistence."""
    return str(uuid.uuid4())


def _cited_chunk_to_json(chunk: CitedChunk) -> dict[str, object]:
    retrieval_method = getattr(chunk.retrieval_method, "value", chunk.retrieval_method)
    return {
        "source_id": chunk.source_id,
        "chunk_id": str(chunk.chunk_id),
        "document_id": str(chunk.document_id),
        "content": chunk.content,
        "filename": chunk.filename,
        "page": chunk.page,
        "section": chunk.section,
        "token_count": chunk.token_count,
        "score": chunk.score,
        "retrieval_method": retrieval_method,
        "metadata": chunk.metadata,
    }
