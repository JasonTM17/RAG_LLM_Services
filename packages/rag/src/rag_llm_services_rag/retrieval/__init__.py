"""Retrieval package: types, retrievers, rank fusion, reranking, and context selection."""

from rag_llm_services_rag.retrieval.context import ContextBuilder, format_source_header
from rag_llm_services_rag.retrieval.fusion import ReciprocalRankFusion
from rag_llm_services_rag.retrieval.keyword import InMemoryKeywordBackend, KeywordRetriever
from rag_llm_services_rag.retrieval.query import QueryNormalizer, normalize_query
from rag_llm_services_rag.retrieval.reranker import (
    BGERerankerProvider,
    FakeRerankerProvider,
    NullRerankerProvider,
    RerankerProvider,
)
from rag_llm_services_rag.retrieval.types import (
    CandidateChunk,
    CitedChunk,
    ContextBundle,
    RetrievalFilter,
    RetrievalMethod,
    RetrievalResult,
)
from rag_llm_services_rag.retrieval.vector import (
    InMemoryVectorBackend,
    VectorRetriever,
    cosine_similarity,
)

__all__ = [
    "BGERerankerProvider",
    "CandidateChunk",
    "CitedChunk",
    "ContextBuilder",
    "ContextBundle",
    "FakeRerankerProvider",
    "InMemoryKeywordBackend",
    "InMemoryVectorBackend",
    "KeywordRetriever",
    "NullRerankerProvider",
    "QueryNormalizer",
    "ReciprocalRankFusion",
    "RerankerProvider",
    "RetrievalFilter",
    "RetrievalMethod",
    "RetrievalResult",
    "VectorRetriever",
    "cosine_similarity",
    "format_source_header",
    "normalize_query",
]
