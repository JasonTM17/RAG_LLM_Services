"""Unit tests for query normalization, fake reranker, null reranker, and standalone retrievers."""

from __future__ import annotations

import uuid

from rag_llm_services_embeddings.fake import FakeEmbeddingProvider
from rag_llm_services_rag.retrieval.keyword import InMemoryKeywordBackend, KeywordRetriever
from rag_llm_services_rag.retrieval.query import QueryNormalizer, normalize_query
from rag_llm_services_rag.retrieval.reranker import (
    BGERerankerProvider,
    FakeRerankerProvider,
    NullRerankerProvider,
)
from rag_llm_services_rag.retrieval.types import (
    RetrievalMethod,
    RetrievalResult,
)
from rag_llm_services_rag.retrieval.vector import InMemoryVectorBackend, VectorRetriever


def test_normalize_query_strips_control_characters() -> None:
    raw = "bảo mật\x00 hệ thống\x1f và\x0b an ninh"
    cleaned = normalize_query(raw)
    assert cleaned == "bảo mật hệ thống và an ninh"
    assert "\x00" not in cleaned
    assert "\x1f" not in cleaned


def test_normalize_query_handles_unbalanced_quotes() -> None:
    # Odd number of quotes: 1 quote
    odd_quote = 'tìm kiếm "tài liệu kỹ thuật'
    cleaned = normalize_query(odd_quote)
    assert cleaned.count('"') == 0
    assert "tìm kiếm tài liệu kỹ thuật" in cleaned

    # Balanced quotes: 2 quotes preserved for websearch_to_tsquery phrase matching
    balanced = 'tìm kiếm "tài liệu kỹ thuật" hôm nay'
    cleaned_balanced = normalize_query(balanced)
    assert cleaned_balanced == 'tìm kiếm "tài liệu kỹ thuật" hôm nay'


def test_normalize_query_collapses_whitespace() -> None:
    raw = "   nhiều     khoảng   \t\n  trắng   "
    assert normalize_query(raw) == "nhiều khoảng trắng"
    assert normalize_query("") == ""
    assert normalize_query("   ") == ""


def test_query_normalizer_length_capping() -> None:
    normalizer = QueryNormalizer(max_length=20)
    long_query = "Đây là một câu truy vấn rất dài vượt quá giới hạn"
    cleaned = normalizer.normalize(long_query)
    assert len(cleaned) <= 20


async def test_fake_reranker_reorders_by_lexical_relevance() -> None:
    reranker = FakeRerankerProvider()

    c_relevant = RetrievalResult(
        chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        content="Hướng dẫn cài đặt Docker và triển khai PostgreSQL database.",
        score=0.3,
        retrieval_method=RetrievalMethod.VECTOR,
        rank=2,
    )
    c_irrelevant = RetrievalResult(
        chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        content="Công thức nấu phở truyền thống tại Hà Nội.",
        score=0.9,
        retrieval_method=RetrievalMethod.VECTOR,
        rank=1,
    )

    query = "cài đặt PostgreSQL database"
    reranked = await reranker.rerank(query, [c_irrelevant, c_relevant])

    assert len(reranked) == 2
    # c_relevant contains all query words, so it should be promoted to #1
    assert reranked[0].chunk_id == c_relevant.chunk_id
    assert reranked[0].rank == 1
    assert reranked[1].chunk_id == c_irrelevant.chunk_id
    assert reranked[1].rank == 2


async def test_fake_reranker_custom_scorer() -> None:
    custom_scorer = lambda q, c: 1.0 if "vip" in c.content else 0.1
    reranker = FakeRerankerProvider(custom_scorer=custom_scorer)

    c1 = RetrievalResult(
        chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        content="ordinary",
        score=0.5,
        retrieval_method=RetrievalMethod.VECTOR,
    )
    c2 = RetrievalResult(
        chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        content="vip content",
        score=0.2,
        retrieval_method=RetrievalMethod.VECTOR,
    )

    reranked = await reranker.rerank("any query", [c1, c2])
    assert reranked[0].chunk_id == c2.chunk_id
    assert reranked[0].score == 1.0


async def test_null_reranker_preserves_order() -> None:
    reranker = NullRerankerProvider()
    c1 = RetrievalResult(
        chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        content="c1",
        score=0.8,
        retrieval_method=RetrievalMethod.VECTOR,
        rank=1,
    )
    c2 = RetrievalResult(
        chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        content="c2",
        score=0.6,
        retrieval_method=RetrievalMethod.VECTOR,
        rank=2,
    )

    res = await reranker.rerank("query", [c1, c2], top_k=1)
    assert len(res) == 1
    assert res[0].chunk_id == c1.chunk_id


async def test_bge_reranker_with_mock_runner() -> None:
    def mock_runner(pairs: list[tuple[str, str]]) -> list[float]:
        return [0.95 if "target" in pair[1] else 0.1 for pair in pairs]

    bge_reranker = BGERerankerProvider(model_runner=mock_runner)
    c1 = RetrievalResult(
        chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        content="unrelated text",
        score=0.5,
        retrieval_method=RetrievalMethod.VECTOR,
    )
    c2 = RetrievalResult(
        chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        content="target chunk",
        score=0.2,
        retrieval_method=RetrievalMethod.VECTOR,
    )

    reranked = await bge_reranker.rerank("query", [c1, c2])
    assert reranked[0].chunk_id == c2.chunk_id
    assert reranked[0].score == 0.95


async def test_vector_retriever_standalone() -> None:
    embed_provider = FakeEmbeddingProvider(dimension=1024)
    backend = InMemoryVectorBackend()
    owner_id = uuid.uuid4()
    doc_id = uuid.uuid4()
    kb_id = uuid.uuid4()

    q_vec = await embed_provider.embed_query("machine learning")
    backend.add_chunk(
        chunk_id=uuid.uuid4(),
        document_id=doc_id,
        content="Deep learning and machine learning models",
        embedding=q_vec,
        owner_id=owner_id,
        filename="ai.txt",
        metadata={"knowledge_base_id": kb_id},
    )

    retriever = VectorRetriever(embedding_provider=embed_provider, search_backend=backend)
    results = await retriever.retrieve("machine learning", owner_id=owner_id, top_k=5)

    assert len(results) == 1
    assert results[0].retrieval_method == RetrievalMethod.VECTOR
    assert "machine learning" in results[0].content


async def test_keyword_retriever_standalone() -> None:
    backend = InMemoryKeywordBackend()
    owner_id = uuid.uuid4()
    doc_id = uuid.uuid4()

    backend.add_chunk(
        chunk_id=uuid.uuid4(),
        document_id=doc_id,
        content="Error code ERR_AUTHENTICATION_FAILED in module auth",
        owner_id=owner_id,
        filename="logs.txt",
    )

    retriever = KeywordRetriever(search_backend=backend)
    results = await retriever.retrieve("ERR_AUTHENTICATION_FAILED", owner_id=owner_id)

    assert len(results) == 1
    assert results[0].retrieval_method == RetrievalMethod.KEYWORD
    assert "ERR_AUTHENTICATION_FAILED" in results[0].content
