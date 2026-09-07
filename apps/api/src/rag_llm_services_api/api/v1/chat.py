"""API router for retrieval-grounded chat endpoints."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from rag_llm_services_api.api.dependencies.auth import get_current_user_id
from rag_llm_services_api.api.v1.retrieval import get_retrieval_service
from rag_llm_services_api.api.v1.schemas.chat import ChatRequest, ChatResponse, LLMUsageResponse
from rag_llm_services_api.api.v1.schemas.retrieval import CitedChunkResponse
from rag_llm_services_api.application.chat_service import (
    ChatApplicationService,
    stream_chunk_to_json,
)
from rag_llm_services_api.core.config import Settings, get_settings
from rag_llm_services_api.db.session import get_session
from rag_llm_services_api.infrastructure.llm import get_llm_provider
from rag_llm_services_api.infrastructure.repositories.chat import ChatRepository
from rag_llm_services_llm.base import LLMProvider
from rag_llm_services_observability.context import get_request_id

router = APIRouter(prefix="/chat", tags=["chat"])


def get_chat_service(
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    llm_provider: Annotated[LLMProvider, Depends(get_llm_provider)],
) -> ChatApplicationService:
    """Dependency assembling the ChatApplicationService."""
    return ChatApplicationService(
        chat_repo=ChatRepository(session),
        retrieval_service=get_retrieval_service(session=session, settings=settings),
        llm_provider=llm_provider,
    )


@router.post("", response_model=ChatResponse)
async def chat(
    payload: ChatRequest,
    owner_id: Annotated[UUID, Depends(get_current_user_id)],
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    service: Annotated[ChatApplicationService, Depends(get_chat_service)],
) -> ChatResponse:
    """Answer one retrieval-grounded chat message."""
    try:
        result = await service.answer(
            owner_id=owner_id,
            message=payload.message,
            conversation_id=payload.conversation_id,
            knowledge_base_id=payload.knowledge_base_id,
            max_output_tokens=payload.max_output_tokens,
            context_token_budget=payload.context_token_budget,
        )
        await session.commit()
    except Exception:
        await session.rollback()
        raise

    request_id = getattr(request.state, "request_id", None) or get_request_id()
    return ChatResponse(
        conversation_id=result.conversation_id,
        message_id=result.message_id,
        answer=result.answer,
        citations=[CitedChunkResponse.model_validate(chunk) for chunk in result.citations],
        retrieved_sources=[
            CitedChunkResponse.model_validate(chunk) for chunk in result.retrieved_sources
        ],
        usage=LLMUsageResponse(**result.usage.__dict__),
        request_id=request_id,
        provider=result.provider,
        model=result.model,
        latency_ms=result.latency_ms,
        retry_count=result.retry_count,
    )


@router.post("/stream")
async def chat_stream(
    payload: ChatRequest,
    owner_id: Annotated[UUID, Depends(get_current_user_id)],
    session: Annotated[AsyncSession, Depends(get_session)],
    service: Annotated[ChatApplicationService, Depends(get_chat_service)],
) -> StreamingResponse:
    """Stream one retrieval-grounded chat answer as semantic SSE events."""

    async def event_stream():
        try:
            async for chunk in service.stream_answer(
                owner_id=owner_id,
                message=payload.message,
                conversation_id=payload.conversation_id,
                knowledge_base_id=payload.knowledge_base_id,
                max_output_tokens=payload.max_output_tokens,
                context_token_budget=payload.context_token_budget,
            ):
                yield f"event: {chunk.event}\ndata: {stream_chunk_to_json(chunk)}\n\n"
            await session.commit()
        except Exception:
            await session.rollback()
            raise

    return StreamingResponse(event_stream(), media_type="text/event-stream")
