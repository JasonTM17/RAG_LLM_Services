"""Pydantic schemas for agent-backed study APIs."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field

from rag_llm_services_agents.study_agent import StudyDifficulty
from rag_llm_services_api.api.v1.schemas.retrieval import CitedChunkResponse


class StudyBaseRequest(BaseModel):
    """Common request body for study generation endpoints."""

    topic: str = Field(..., min_length=1, max_length=2000)
    conversation_id: UUID | None = None
    knowledge_base_id: UUID | None = None
    difficulty: StudyDifficulty = StudyDifficulty.INTERMEDIATE
    max_output_tokens: int | None = Field(default=None, ge=1, le=8192)
    context_token_budget: int | None = Field(default=None, ge=100, le=32000)


class QuizRequest(StudyBaseRequest):
    """Request body for POST /api/v1/study/quiz."""

    question_count: int = Field(default=5, ge=1, le=20)


class FlashcardRequest(StudyBaseRequest):
    """Request body for POST /api/v1/study/flashcards."""

    card_count: int = Field(default=10, ge=1, le=50)


class LearningPlanRequest(StudyBaseRequest):
    """Request body for POST /api/v1/study/learning-plan."""

    days: int = Field(default=7, ge=1, le=30)


class QuizQuestionResponse(BaseModel):
    """One quiz question returned by the study API."""

    question: str
    choices: list[str]
    answer: str
    explanation: str
    citations: list[str]


class FlashcardResponse(BaseModel):
    """One flashcard returned by the study API."""

    front: str
    back: str
    citations: list[str]


class LearningPlanDayResponse(BaseModel):
    """One day returned by the learning-plan API."""

    day: int
    objective: str
    activities: list[str]
    check_yourself: str
    citations: list[str]


class StudyResponseBase(BaseModel):
    """Common response metadata for study endpoints."""

    conversation_id: UUID
    message_id: UUID
    topic: str
    difficulty: StudyDifficulty
    retrieved_sources: list[CitedChunkResponse] = Field(default_factory=list)
    request_id: str | None = None
    provider: str
    model: str


class QuizResponse(StudyResponseBase):
    """Response body for POST /api/v1/study/quiz."""

    questions: list[QuizQuestionResponse]


class FlashcardSetResponse(StudyResponseBase):
    """Response body for POST /api/v1/study/flashcards."""

    cards: list[FlashcardResponse]


class LearningPlanResponse(StudyResponseBase):
    """Response body for POST /api/v1/study/learning-plan."""

    days: list[LearningPlanDayResponse]
