"""Database models export and registration."""

from rag_llm_services_api.db.base import Base
from rag_llm_services_api.db.models.automation import AutomationReportModel, EvaluationRunModel
from rag_llm_services_api.db.models.chunk import DocumentChunkModel
from rag_llm_services_api.db.models.conversation import ConversationModel, MessageModel
from rag_llm_services_api.db.models.document import DocumentModel, DocumentVersionModel
from rag_llm_services_api.db.models.ingestion_job import IngestionJobModel
from rag_llm_services_api.db.models.knowledge_base import KnowledgeBaseModel
from rag_llm_services_api.db.models.llm_usage import LLMUsageModel
from rag_llm_services_api.db.models.rag_query import RagQueryModel

__all__ = [
    "AutomationReportModel",
    "Base",
    "ConversationModel",
    "DocumentChunkModel",
    "DocumentModel",
    "DocumentVersionModel",
    "EvaluationRunModel",
    "IngestionJobModel",
    "KnowledgeBaseModel",
    "LLMUsageModel",
    "MessageModel",
    "RagQueryModel",
]
