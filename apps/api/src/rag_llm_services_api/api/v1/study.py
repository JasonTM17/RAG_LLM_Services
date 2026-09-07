"""API router for agent-backed study workflows."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from rag_llm_services_api.api.dependencies.auth import get_current_user_id
from rag_llm_services_api.api.v1.retrieval import get_retrieval_service
from rag_llm_services_api.api.v1.schemas.retrieval import CitedChunkResponse
from rag_llm_services_api.api.v1.schemas.study import (
    FlashcardRequest,
    FlashcardResponse,
    FlashcardSetResponse,
    LearningPlanDayResponse,
    LearningPlanRequest,
    LearningPlanResponse,
    QuizQuestionResponse,
    QuizRequest,
    QuizResponse,
)
from rag_llm_services_api.application.agent_service import (
    AgentApplicationService,
    DocumentCatalogApplicationService,
)
from rag_llm_services_api.core.config import Settings, get_settings
from rag_llm_services_api.db.session import get_session
from rag_llm_services_api.infrastructure.llm import get_llm_provider
from rag_llm_services_api.infrastructure.repositories.chat import ChatRepository
from rag_llm_services_api.infrastructure.repositories.documents import DocumentRepository
from rag_llm_services_api.infrastructure.repositories.knowledge_bases import KnowledgeBaseRepository
from rag_llm_services_llm.base import LLMProvider
from rag_llm_services_observability.context import get_request_id

router = APIRouter(prefix="/study", tags=["study"])


def get_agent_service(
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    llm_provider: Annotated[LLMProvider, Depends(get_llm_provider)],
) -> AgentApplicationService:
    """Dependency assembling study agent workflows."""
    document_repo = DocumentRepository(session)
    knowledge_base_repo = KnowledgeBaseRepository(session)
    return AgentApplicationService(
        chat_repo=ChatRepository(session),
        retrieval_service=get_retrieval_service(session=session, settings=settings),
        document_catalog=DocumentCatalogApplicationService(
            document_repo=document_repo,
            knowledge_base_repo=knowledge_base_repo,
        ),
        llm_provider=llm_provider,
        settings=settings,
    )


@router.post("/quiz", response_model=QuizResponse)
async def create_quiz(
    payload: QuizRequest,
    owner_id: Annotated[UUID, Depends(get_current_user_id)],
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    service: Annotated[AgentApplicationService, Depends(get_agent_service)],
) -> QuizResponse:
    """Generate a source-cited quiz."""
    try:
        result = await service.quiz(
            owner_id=owner_id,
            topic=payload.topic,
            question_count=payload.question_count,
            difficulty=payload.difficulty,
            conversation_id=payload.conversation_id,
            knowledge_base_id=payload.knowledge_base_id,
            max_output_tokens=payload.max_output_tokens,
            context_token_budget=payload.context_token_budget,
        )
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    output = result.output
    return QuizResponse(
        conversation_id=result.conversation_id,
        message_id=result.message_id,
        topic=output.topic,
        difficulty=output.difficulty,
        questions=[QuizQuestionResponse.model_validate(q.model_dump()) for q in output.questions],
        retrieved_sources=_cited_source_responses(result.retrieved_sources),
        request_id=_request_id(request),
        provider=result.provider,
        model=result.model,
    )


@router.post("/flashcards", response_model=FlashcardSetResponse)
async def create_flashcards(
    payload: FlashcardRequest,
    owner_id: Annotated[UUID, Depends(get_current_user_id)],
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    service: Annotated[AgentApplicationService, Depends(get_agent_service)],
) -> FlashcardSetResponse:
    """Generate source-cited flashcards."""
    try:
        result = await service.flashcards(
            owner_id=owner_id,
            topic=payload.topic,
            card_count=payload.card_count,
            difficulty=payload.difficulty,
            conversation_id=payload.conversation_id,
            knowledge_base_id=payload.knowledge_base_id,
            max_output_tokens=payload.max_output_tokens,
            context_token_budget=payload.context_token_budget,
        )
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    output = result.output
    return FlashcardSetResponse(
        conversation_id=result.conversation_id,
        message_id=result.message_id,
        topic=output.topic,
        difficulty=output.difficulty,
        cards=[FlashcardResponse.model_validate(card.model_dump()) for card in output.cards],
        retrieved_sources=_cited_source_responses(result.retrieved_sources),
        request_id=_request_id(request),
        provider=result.provider,
        model=result.model,
    )


@router.post("/learning-plan", response_model=LearningPlanResponse)
async def create_learning_plan(
    payload: LearningPlanRequest,
    owner_id: Annotated[UUID, Depends(get_current_user_id)],
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    service: Annotated[AgentApplicationService, Depends(get_agent_service)],
) -> LearningPlanResponse:
    """Generate a source-cited learning plan."""
    try:
        result = await service.learning_plan(
            owner_id=owner_id,
            topic=payload.topic,
            days=payload.days,
            difficulty=payload.difficulty,
            conversation_id=payload.conversation_id,
            knowledge_base_id=payload.knowledge_base_id,
            max_output_tokens=payload.max_output_tokens,
            context_token_budget=payload.context_token_budget,
        )
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    output = result.output
    return LearningPlanResponse(
        conversation_id=result.conversation_id,
        message_id=result.message_id,
        topic=output.topic,
        difficulty=output.difficulty,
        days=[LearningPlanDayResponse.model_validate(day.model_dump()) for day in output.days],
        retrieved_sources=_cited_source_responses(result.retrieved_sources),
        request_id=_request_id(request),
        provider=result.provider,
        model=result.model,
    )


def _request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None) or get_request_id()


def _cited_source_responses(sources) -> list[CitedChunkResponse]:
    return [CitedChunkResponse.model_validate(source.to_cited_chunk()) for source in sources]
