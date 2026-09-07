"""Database models export and registration."""

from rag_llm_services_api.db.base import Base
from rag_llm_services_api.db.models.chunk import DocumentChunkModel
from rag_llm_services_api.db.models.document import DocumentModel, DocumentVersionModel
from rag_llm_services_api.db.models.ingestion_job import IngestionJobModel
from rag_llm_services_api.db.models.knowledge_base import KnowledgeBaseModel

__all__ = [
    "Base",
    "DocumentChunkModel",
    "DocumentModel",
    "DocumentVersionModel",
    "IngestionJobModel",
    "KnowledgeBaseModel",
]
