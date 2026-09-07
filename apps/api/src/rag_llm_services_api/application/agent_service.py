"""Application service for agent-backed study workflows."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TypeVar
from uuid import UUID

from pydantic import BaseModel

from rag_llm_services_agents.citations import CitationValidationError
from rag_llm_services_agents.context_window import ContextWindowManager
from rag_llm_services_agents.study_agent import (
    FlashcardSet,
    LearningPlan,
    Quiz,
    StudyAgent,
    StudyDifficulty,
)
from rag_llm_services_agents.tools import (
    AgentToolLimits,
    AgentToolScopeError,
    DocumentMetadata,
    KnowledgeBaseTools,
    SourceChunk,
)
from rag_llm_services_api.application.retrieval_service import RetrievalService
from rag_llm_services_api.core.config import Settings
from rag_llm_services_api.core.errors import NotFoundError, ValidationError
from rag_llm_services_api.domain.chat import ChatMessageRole
from rag_llm_services_api.infrastructure.repositories.chat import ChatRepository
from rag_llm_services_api.infrastructure.repositories.documents import DocumentRepository
from rag_llm_services_api.infrastructure.repositories.knowledge_bases import KnowledgeBaseRepository
from rag_llm_services_llm.base import LLMProvider

StudyOutputT = TypeVar("StudyOutputT", bound=BaseModel)


@dataclass(frozen=True)
class StudyWorkflowResult[StudyOutputT]:
    """Persisted study workflow response."""

    conversation_id: UUID
    message_id: UUID
    output: StudyOutputT
    retrieved_sources: list[SourceChunk]
    provider: str
    model: str


class DocumentCatalogApplicationService:
    """Owner-scoped document catalog exposed to agent tools."""

    def __init__(
        self,
        *,
        document_repo: DocumentRepository,
        knowledge_base_repo: KnowledgeBaseRepository,
    ) -> None:
        self._document_repo = document_repo
        self._knowledge_base_repo = knowledge_base_repo

    async def list_documents(
        self,
        *,
        owner_id: UUID,
        knowledge_base_id: UUID | None,
        limit: int,
    ) -> list[DocumentMetadata]:
        """List owner-scoped document metadata for agents."""
        if knowledge_base_id is not None:
            kb = await self._knowledge_base_repo.get_by_id(owner_id, knowledge_base_id)
            if kb is None:
                raise NotFoundError("Knowledge base not found")
        docs = await self._document_repo.list_documents(
            owner_id=owner_id,
            knowledge_base_id=knowledge_base_id,
            limit=limit,
        )
        return [
            DocumentMetadata(
                id=doc.id,
                knowledge_base_id=doc.knowledge_base_id,
                filename=doc.filename,
                content_type=doc.content_type,
                status=doc.status,
                created_at=doc.created_at,
                updated_at=doc.updated_at,
                current_version_id=doc.current_version_id,
            )
            for doc in docs
        ]

    async def get_document_metadata(
        self,
        *,
        owner_id: UUID,
        document_id: UUID,
    ) -> DocumentMetadata | None:
        """Fetch one owner-scoped document metadata record for agents."""
        doc = await self._document_repo.get_document_by_id(owner_id, document_id)
        if doc is None:
            return None
        return DocumentMetadata(
            id=doc.id,
            knowledge_base_id=doc.knowledge_base_id,
            filename=doc.filename,
            content_type=doc.content_type,
            status=doc.status,
            created_at=doc.created_at,
            updated_at=doc.updated_at,
            current_version_id=doc.current_version_id,
        )


class AgentApplicationService:
    """Coordinates local memory, bounded tools, and study agents."""

    def __init__(
        self,
        *,
        chat_repo: ChatRepository,
        retrieval_service: RetrievalService,
        document_catalog: DocumentCatalogApplicationService,
        llm_provider: LLMProvider,
        settings: Settings,
    ) -> None:
        self._chat_repo = chat_repo
        limits = AgentToolLimits(
            max_results=settings.agents.tool_max_results,
            max_context_chunks=settings.agents.tool_max_context_chunks,
            max_chunk_chars=settings.agents.tool_max_chunk_chars,
            max_context_chars=settings.agents.tool_max_context_chars,
            max_documents=settings.agents.tool_max_documents,
        )
        context_window = ContextWindowManager(
            max_messages=settings.agents.history_max_messages,
            max_chars=settings.agents.history_max_chars,
        )
        tools = KnowledgeBaseTools(
            retrieval_service=retrieval_service,
            document_catalog=document_catalog,
            limits=limits,
        )
        self._study_agent = StudyAgent(
            tools=tools,
            llm_provider=llm_provider,
            context_window=context_window,
        )
        self._history_limit = settings.agents.history_max_messages

    async def quiz(
        self,
        *,
        owner_id: UUID,
        topic: str,
        question_count: int,
        difficulty: StudyDifficulty,
        conversation_id: UUID | None,
        knowledge_base_id: UUID | None,
        max_output_tokens: int | None,
        context_token_budget: int | None,
    ) -> StudyWorkflowResult[Quiz]:
        conversation_id, user_message_id, history = await self._prepare_run(
            owner_id=owner_id,
            conversation_id=conversation_id,
            title_prefix="Quiz",
            topic=topic,
        )
        try:
            result = await self._study_agent.quiz(
                owner_id=owner_id,
                topic=topic,
                question_count=question_count,
                difficulty=difficulty,
                conversation_history=history,
                knowledge_base_id=knowledge_base_id,
                max_output_tokens=max_output_tokens,
                context_token_budget=context_token_budget,
                idempotency_key=str(user_message_id),
            )
        except (CitationValidationError, AgentToolScopeError) as exc:
            raise ValidationError(
                "Study workflow failed validation",
                code="STUDY_WORKFLOW_INVALID",
                status_code=422,
            ) from exc
        return await self._persist_result(
            owner_id=owner_id,
            conversation_id=conversation_id,
            result=result.output,
            retrieved_sources=result.retrieved_sources,
            provider=result.provider,
            model=result.model,
        )

    async def flashcards(
        self,
        *,
        owner_id: UUID,
        topic: str,
        card_count: int,
        difficulty: StudyDifficulty,
        conversation_id: UUID | None,
        knowledge_base_id: UUID | None,
        max_output_tokens: int | None,
        context_token_budget: int | None,
    ) -> StudyWorkflowResult[FlashcardSet]:
        conversation_id, user_message_id, history = await self._prepare_run(
            owner_id=owner_id,
            conversation_id=conversation_id,
            title_prefix="Flashcards",
            topic=topic,
        )
        try:
            result = await self._study_agent.flashcards(
                owner_id=owner_id,
                topic=topic,
                card_count=card_count,
                difficulty=difficulty,
                conversation_history=history,
                knowledge_base_id=knowledge_base_id,
                max_output_tokens=max_output_tokens,
                context_token_budget=context_token_budget,
                idempotency_key=str(user_message_id),
            )
        except (CitationValidationError, AgentToolScopeError) as exc:
            raise ValidationError(
                "Study workflow failed validation",
                code="STUDY_WORKFLOW_INVALID",
                status_code=422,
            ) from exc
        return await self._persist_result(
            owner_id=owner_id,
            conversation_id=conversation_id,
            result=result.output,
            retrieved_sources=result.retrieved_sources,
            provider=result.provider,
            model=result.model,
        )

    async def learning_plan(
        self,
        *,
        owner_id: UUID,
        topic: str,
        days: int,
        difficulty: StudyDifficulty,
        conversation_id: UUID | None,
        knowledge_base_id: UUID | None,
        max_output_tokens: int | None,
        context_token_budget: int | None,
    ) -> StudyWorkflowResult[LearningPlan]:
        conversation_id, user_message_id, history = await self._prepare_run(
            owner_id=owner_id,
            conversation_id=conversation_id,
            title_prefix="Learning plan",
            topic=topic,
        )
        try:
            result = await self._study_agent.learning_plan(
                owner_id=owner_id,
                topic=topic,
                days=days,
                difficulty=difficulty,
                conversation_history=history,
                knowledge_base_id=knowledge_base_id,
                max_output_tokens=max_output_tokens,
                context_token_budget=context_token_budget,
                idempotency_key=str(user_message_id),
            )
        except (CitationValidationError, AgentToolScopeError) as exc:
            raise ValidationError(
                "Study workflow failed validation",
                code="STUDY_WORKFLOW_INVALID",
                status_code=422,
            ) from exc
        return await self._persist_result(
            owner_id=owner_id,
            conversation_id=conversation_id,
            result=result.output,
            retrieved_sources=result.retrieved_sources,
            provider=result.provider,
            model=result.model,
        )

    async def _prepare_run(
        self,
        *,
        owner_id: UUID,
        conversation_id: UUID | None,
        title_prefix: str,
        topic: str,
    ) -> tuple[UUID, UUID, list[tuple[str, str]]]:
        resolved_id = await self._resolve_conversation(
            owner_id=owner_id,
            conversation_id=conversation_id,
            title=f"{title_prefix}: {topic.strip()[:64]}"[:80],
        )
        history = await self._history(owner_id=owner_id, conversation_id=resolved_id)
        user_message = await self._chat_repo.add_message(
            owner_id=owner_id,
            conversation_id=resolved_id,
            role=ChatMessageRole.USER.value,
            content=topic,
            metadata_json={"workflow": title_prefix.lower().replace(" ", "_")},
        )
        return resolved_id, user_message.id, history

    async def _resolve_conversation(
        self,
        *,
        owner_id: UUID,
        conversation_id: UUID | None,
        title: str,
    ) -> UUID:
        if conversation_id is not None:
            conversation = await self._chat_repo.get_conversation(
                owner_id=owner_id,
                conversation_id=conversation_id,
            )
            if conversation is None:
                raise NotFoundError("Conversation not found")
            return conversation.id
        conversation = await self._chat_repo.create_conversation(
            owner_id=owner_id,
            title=title or "Study workflow",
        )
        return conversation.id

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

    async def _persist_result(
        self,
        *,
        owner_id: UUID,
        conversation_id: UUID,
        result: StudyOutputT,
        retrieved_sources: list[SourceChunk],
        provider: str,
        model: str,
    ) -> StudyWorkflowResult[StudyOutputT]:
        assistant_message = await self._chat_repo.add_message(
            owner_id=owner_id,
            conversation_id=conversation_id,
            role=ChatMessageRole.ASSISTANT.value,
            content=result.model_dump_json(),
            metadata_json={
                "provider": provider,
                "model": model,
                "source_ids": [source.source_id for source in retrieved_sources],
            },
        )
        return StudyWorkflowResult(
            conversation_id=conversation_id,
            message_id=assistant_message.id,
            output=result,
            retrieved_sources=retrieved_sources,
            provider=provider,
            model=model,
        )
