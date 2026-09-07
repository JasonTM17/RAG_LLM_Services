"""Pydantic request and response schemas for API v1."""

from rag_llm_services_api.api.v1.schemas.chat import (
    ChatRequest,
    ChatResponse,
    LLMUsageResponse,
)
from rag_llm_services_api.api.v1.schemas.documents import (
    DocumentDetailResponse,
    DocumentResponse,
    DocumentUploadResponse,
    DocumentVersionResponse,
    IngestionJobResponse,
)
from rag_llm_services_api.api.v1.schemas.knowledge_bases import (
    KnowledgeBaseCreate,
    KnowledgeBaseResponse,
    KnowledgeBaseUpdate,
)
from rag_llm_services_api.api.v1.schemas.retrieval import (
    CitedChunkResponse,
    ContextBundleResponse,
    RetrievalChunkResponse,
    RetrievalFilterSchema,
    RetrievalSearchRequest,
    RetrievalSearchResponse,
)
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
    StudyBaseRequest,
)

__all__ = [
    "ChatRequest",
    "ChatResponse",
    "CitedChunkResponse",
    "ContextBundleResponse",
    "DocumentDetailResponse",
    "DocumentResponse",
    "DocumentUploadResponse",
    "DocumentVersionResponse",
    "FlashcardRequest",
    "FlashcardResponse",
    "FlashcardSetResponse",
    "IngestionJobResponse",
    "KnowledgeBaseCreate",
    "KnowledgeBaseResponse",
    "KnowledgeBaseUpdate",
    "LLMUsageResponse",
    "LearningPlanDayResponse",
    "LearningPlanRequest",
    "LearningPlanResponse",
    "QuizQuestionResponse",
    "QuizRequest",
    "QuizResponse",
    "RetrievalChunkResponse",
    "RetrievalFilterSchema",
    "RetrievalSearchRequest",
    "RetrievalSearchResponse",
    "StudyBaseRequest",
]
