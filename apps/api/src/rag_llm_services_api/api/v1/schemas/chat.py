"""Pydantic schemas for retrieval-grounded chat APIs."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field

from rag_llm_services_api.api.v1.schemas.retrieval import CitedChunkResponse


class ChatRequest(BaseModel):
    """Request body for POST /api/v1/chat and /api/v1/chat/stream."""

    message: str = Field(..., min_length=1, max_length=8000)
    conversation_id: UUID | None = None
    knowledge_base_id: UUID | None = None
    max_output_tokens: int | None = Field(default=None, ge=1, le=8192)
    context_token_budget: int | None = Field(default=None, ge=100, le=32000)


class LLMUsageResponse(BaseModel):
    """LLM token usage and estimated cost returned to API clients."""

    input_tokens: int = 0
    output_tokens: int = 0
    cached_input_tokens: int = 0
    total_tokens: int = 0
    estimated_cost_usd: float = 0.0


class ChatResponse(BaseModel):
    """Response body for a completed retrieval-grounded chat answer."""

    conversation_id: UUID
    message_id: UUID
    answer: str
    citations: list[CitedChunkResponse] = Field(default_factory=list)
    retrieved_sources: list[CitedChunkResponse] = Field(default_factory=list)
    usage: LLMUsageResponse
    request_id: str | None = None
    provider: str
    model: str
    latency_ms: float = 0.0
    retry_count: int = 0
