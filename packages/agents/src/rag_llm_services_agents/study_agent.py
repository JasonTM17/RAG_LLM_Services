"""Study workflow agent outputs backed by bounded RAG context."""

from __future__ import annotations

import logging
import time
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import TypeVar
from uuid import UUID

from pydantic import BaseModel, Field
from pydantic import ValidationError as PydanticValidationError

from rag_llm_services_agents.citations import CitationValidationError, CitationValidator
from rag_llm_services_agents.context_window import ContextWindowManager, HistoryMessage
from rag_llm_services_agents.prompts import STUDY_INSTRUCTIONS, build_study_user_prompt
from rag_llm_services_agents.tools import KnowledgeBaseTools, SearchKnowledgeBaseInput, SourceChunk
from rag_llm_services_llm.base import LLMMessage, LLMProvider, LLMRequest, MessageRole
from rag_llm_services_llm.errors import LLMProviderError
from rag_llm_services_observability.metrics import record_error, record_llm_request

logger = logging.getLogger(__name__)

StudyOutputT = TypeVar("StudyOutputT", bound=BaseModel)


class StudyDifficulty(StrEnum):
    """Supported study material difficulty levels."""

    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"


class QuizQuestion(BaseModel):
    """One quiz question grounded in cited source context."""

    question: str = Field(..., min_length=1)
    choices: list[str] = Field(..., min_length=2, max_length=6)
    answer: str = Field(..., min_length=1)
    explanation: str = Field(..., min_length=1)
    citations: list[str] = Field(..., min_length=1, max_length=5)


class Quiz(BaseModel):
    """Quiz generated from source context."""

    topic: str
    difficulty: StudyDifficulty
    questions: list[QuizQuestion] = Field(..., min_length=1, max_length=20)


class Flashcard(BaseModel):
    """One flashcard grounded in cited source context."""

    front: str = Field(..., min_length=1)
    back: str = Field(..., min_length=1)
    citations: list[str] = Field(..., min_length=1, max_length=5)


class FlashcardSet(BaseModel):
    """Flashcard set generated from source context."""

    topic: str
    difficulty: StudyDifficulty
    cards: list[Flashcard] = Field(..., min_length=1, max_length=50)


class LearningPlanDay(BaseModel):
    """One day in a source-grounded learning plan."""

    day: int = Field(..., ge=1)
    objective: str = Field(..., min_length=1)
    activities: list[str] = Field(..., min_length=1, max_length=6)
    check_yourself: str = Field(..., min_length=1)
    citations: list[str] = Field(..., min_length=1, max_length=5)


class LearningPlan(BaseModel):
    """Learning plan generated from source context."""

    topic: str
    difficulty: StudyDifficulty
    days: list[LearningPlanDay] = Field(..., min_length=1, max_length=30)


@dataclass(frozen=True)
class StudyAgentResult[StudyOutputT]:
    """Structured study output plus retrieval provenance."""

    output: StudyOutputT
    retrieved_sources: list[SourceChunk]
    provider: str
    model: str


class StudyAgent:
    """Generate quiz, flashcards, and learning plans through bounded RAG context."""

    def __init__(
        self,
        *,
        tools: KnowledgeBaseTools,
        llm_provider: LLMProvider,
        citation_validator: CitationValidator | None = None,
        context_window: ContextWindowManager | None = None,
    ) -> None:
        self._tools = tools
        self._llm_provider = llm_provider
        self._citation_validator = citation_validator or CitationValidator()
        self._context_window = context_window or ContextWindowManager()

    async def quiz(
        self,
        *,
        owner_id: UUID,
        topic: str,
        question_count: int,
        difficulty: StudyDifficulty,
        conversation_history: Sequence[HistoryMessage | tuple[str, str]] | None = None,
        knowledge_base_id: UUID | None = None,
        max_output_tokens: int | None = None,
        context_token_budget: int | None = None,
        idempotency_key: str | None = None,
    ) -> StudyAgentResult[Quiz]:
        return await self._generate(
            owner_id=owner_id,
            topic=topic,
            task="quiz",
            count=question_count,
            difficulty=difficulty,
            output_type=Quiz,
            conversation_history=conversation_history,
            knowledge_base_id=knowledge_base_id,
            max_output_tokens=max_output_tokens,
            context_token_budget=context_token_budget,
            idempotency_key=idempotency_key,
        )

    async def flashcards(
        self,
        *,
        owner_id: UUID,
        topic: str,
        card_count: int,
        difficulty: StudyDifficulty,
        conversation_history: Sequence[HistoryMessage | tuple[str, str]] | None = None,
        knowledge_base_id: UUID | None = None,
        max_output_tokens: int | None = None,
        context_token_budget: int | None = None,
        idempotency_key: str | None = None,
    ) -> StudyAgentResult[FlashcardSet]:
        return await self._generate(
            owner_id=owner_id,
            topic=topic,
            task="flashcards",
            count=card_count,
            difficulty=difficulty,
            output_type=FlashcardSet,
            conversation_history=conversation_history,
            knowledge_base_id=knowledge_base_id,
            max_output_tokens=max_output_tokens,
            context_token_budget=context_token_budget,
            idempotency_key=idempotency_key,
        )

    async def learning_plan(
        self,
        *,
        owner_id: UUID,
        topic: str,
        days: int,
        difficulty: StudyDifficulty,
        conversation_history: Sequence[HistoryMessage | tuple[str, str]] | None = None,
        knowledge_base_id: UUID | None = None,
        max_output_tokens: int | None = None,
        context_token_budget: int | None = None,
        idempotency_key: str | None = None,
    ) -> StudyAgentResult[LearningPlan]:
        return await self._generate(
            owner_id=owner_id,
            topic=topic,
            task="learning_plan",
            count=days,
            difficulty=difficulty,
            output_type=LearningPlan,
            conversation_history=conversation_history,
            knowledge_base_id=knowledge_base_id,
            max_output_tokens=max_output_tokens,
            context_token_budget=context_token_budget,
            idempotency_key=idempotency_key,
        )

    async def _generate(
        self,
        *,
        owner_id: UUID,
        topic: str,
        task: str,
        count: int,
        difficulty: StudyDifficulty,
        output_type: type[StudyOutputT],
        conversation_history: Sequence[HistoryMessage | tuple[str, str]] | None,
        knowledge_base_id: UUID | None,
        max_output_tokens: int | None,
        context_token_budget: int | None,
        idempotency_key: str | None,
    ) -> StudyAgentResult[StudyOutputT]:
        tool_output = await self._tools.search_knowledge_base(
            owner_id=owner_id,
            payload=SearchKnowledgeBaseInput(
                query=topic,
                knowledge_base_id=knowledge_base_id,
                top_k=self._tools.limits.max_results,
                context_token_budget=context_token_budget,
            ),
        )
        selected_history = self._context_window.select(conversation_history or [])
        messages = (
            LLMMessage(role=MessageRole.SYSTEM, content=STUDY_INSTRUCTIONS),
            LLMMessage(
                role=MessageRole.USER,
                content=build_study_user_prompt(
                    task=task,
                    topic=topic,
                    context_text=tool_output.context_text,
                    difficulty=difficulty.value,
                    count=count,
                    history=selected_history.messages,
                ),
            ),
        )
        capabilities = self._llm_provider.capabilities()
        provider_started = time.perf_counter()
        try:
            structured_response = await self._llm_provider.structured_response(
                LLMRequest(
                    messages=messages,
                    max_output_tokens=max_output_tokens,
                    temperature=0.2,
                    idempotency_key=idempotency_key,
                ),
                schema=output_type.model_json_schema(),
            )
        except Exception:
            elapsed_ms = round((time.perf_counter() - provider_started) * 1000.0, 2)
            record_llm_request(
                provider=capabilities.provider,
                status="failed",
                latency_ms=elapsed_ms,
            )
            record_error("llm", "exception")
            logger.exception(
                "LLM structured request failed",
                extra={
                    "stage": "llm.structured",
                    "dependency": "llm_provider",
                    "provider": capabilities.provider,
                    "model": capabilities.model,
                    "status": "failed",
                    "latency_ms": elapsed_ms,
                    "error_code": "LLM_STRUCTURED_REQUEST_FAILED",
                    "workflow": task,
                },
            )
            raise
        elapsed_ms = round((time.perf_counter() - provider_started) * 1000.0, 2)
        record_llm_request(
            provider=structured_response.provider,
            status="succeeded",
            latency_ms=structured_response.latency_ms or elapsed_ms,
            usage=structured_response.usage,
        )
        logger.info(
            "LLM structured request completed",
            extra={
                "stage": "llm.structured",
                "dependency": "llm_provider",
                "provider": structured_response.provider,
                "model": structured_response.model,
                "status": "succeeded",
                "latency_ms": structured_response.latency_ms or elapsed_ms,
                "workflow": task,
            },
        )
        try:
            output = output_type.model_validate(structured_response.output)
        except PydanticValidationError as exc:
            raise LLMProviderError(
                "LLM provider returned malformed study output",
                code="LLM_MALFORMED_STRUCTURED_OUTPUT",
                status_code=502,
            ) from exc

        self._validate_output_citations(
            output, available_source_ids=[s.source_id for s in tool_output.sources]
        )
        return StudyAgentResult(
            output=output,
            retrieved_sources=tool_output.sources,
            provider=structured_response.provider,
            model=structured_response.model,
        )

    def _validate_output_citations(
        self,
        output: BaseModel,
        *,
        available_source_ids: list[str],
    ) -> None:
        citation_fields = _extract_structured_citations(output)
        for citations in citation_fields:
            self._citation_validator.validate_source_ids(
                citations,
                available_source_ids=available_source_ids,
                require_citation=bool(available_source_ids),
            )
        for text in _extract_structured_text_fields(output):
            self._citation_validator.validate(
                text,
                available_source_ids=available_source_ids,
            )


def _extract_structured_citations(output: BaseModel) -> list[list[str]]:
    if isinstance(output, Quiz):
        return [question.citations for question in output.questions]
    if isinstance(output, FlashcardSet):
        return [card.citations for card in output.cards]
    if isinstance(output, LearningPlan):
        return [day.citations for day in output.days]
    raise CitationValidationError("Unsupported study output type")


def _extract_structured_text_fields(output: BaseModel) -> list[str]:
    if isinstance(output, Quiz):
        return [
            text
            for question in output.questions
            for text in [
                question.question,
                *question.choices,
                question.answer,
                question.explanation,
            ]
        ]
    if isinstance(output, FlashcardSet):
        return [text for card in output.cards for text in [card.front, card.back]]
    if isinstance(output, LearningPlan):
        return [
            text
            for day in output.days
            for text in [
                day.objective,
                *day.activities,
                day.check_yourself,
            ]
        ]
    raise CitationValidationError("Unsupported study output type")
