"""Versioned API surface under /api/v1.

Contract: routers in this package delegate to application services and
declare typed request/response models. They must not execute SQL directly,
construct prompts, or instantiate provider clients. Phase 02 ships the empty
router scaffold; domain routes arrive with their phases (documents Phase 03,
retrieval Phase 05, chat Phase 06/07, study Phase 07).
"""

from fastapi import APIRouter

from rag_llm_services_api.api.v1.chat import router as chat_router
from rag_llm_services_api.api.v1.documents import router as documents_router
from rag_llm_services_api.api.v1.ingestion_jobs import router as ingestion_jobs_router
from rag_llm_services_api.api.v1.knowledge_bases import router as knowledge_bases_router
from rag_llm_services_api.api.v1.retrieval import router as retrieval_router
from rag_llm_services_api.api.v1.study import router as study_router

router = APIRouter()
router.include_router(chat_router)
router.include_router(knowledge_bases_router)
router.include_router(documents_router)
router.include_router(ingestion_jobs_router)
router.include_router(retrieval_router)
router.include_router(study_router)
