"""Integration tests for hybrid retrieval, reranking, filtering, tenant isolation, and search API."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from uuid import UUID

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import rag_llm_services_api.db.models  # noqa: F401
from rag_llm_services_api.application.retrieval_service import RetrievalService
from rag_llm_services_api.core.config import Settings, get_settings
from rag_llm_services_api.db.base import Base
from rag_llm_services_api.db.models.document import DocumentVersionModel
from rag_llm_services_api.db.session import get_session
from rag_llm_services_api.domain.documents import DocumentStatus
from rag_llm_services_api.infrastructure.embeddings import get_embedding_provider
from rag_llm_services_api.infrastructure.repositories.chunks import ChunkCreateData, ChunkRepository
from rag_llm_services_api.infrastructure.repositories.documents import DocumentRepository
from rag_llm_services_api.infrastructure.repositories.knowledge_bases import KnowledgeBaseRepository
from rag_llm_services_api.infrastructure.repositories.rag_queries import RagQueryRepository
from rag_llm_services_api.infrastructure.reranker import get_reranker_provider
from rag_llm_services_api.main import create_app
from rag_llm_services_embeddings.fake import FakeEmbeddingProvider
from rag_llm_services_observability.metrics import (
    RETRIEVAL_QUERY_TOTAL,
    RETRIEVAL_STAGE_LATENCY_MS,
    reset_retrieval_metrics,
)
from rag_llm_services_rag.retrieval.reranker import FakeRerankerProvider, NullRerankerProvider
from rag_llm_services_rag.retrieval.types import (
    RetrievalFilter,
    RetrievalMethod,
)


@pytest.fixture
async def retrieval_env() -> AsyncIterator[
    tuple[
        AsyncSession,
        ChunkRepository,
        RagQueryRepository,
        RetrievalService,
        FakeEmbeddingProvider,
        UUID,
        UUID,
    ]
]:
    """Build isolated in-memory SQLite database, fake embeddings, and RetrievalService."""
    owner_a = uuid.UUID("00000000-0000-0000-0000-000000000001")
    owner_b = uuid.UUID("00000000-0000-0000-0000-000000000002")

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    fake_embeddings = FakeEmbeddingProvider(dimension=1024)
    fake_reranker = FakeRerankerProvider()

    async with session_maker() as session:
        chunk_repo = ChunkRepository(session)
        rag_query_repo = RagQueryRepository(session)
        service = RetrievalService(
            chunk_repo=chunk_repo,
            rag_query_repo=rag_query_repo,
            embedding_provider=fake_embeddings,
            reranker_provider=fake_reranker,
            default_context_budget=4000,
        )

        yield session, chunk_repo, rag_query_repo, service, fake_embeddings, owner_a, owner_b

    await engine.dispose()


@pytest.fixture
async def api_env() -> AsyncIterator[
    tuple[FastAPI, httpx.AsyncClient, AsyncSession, ChunkRepository, UUID, UUID]
]:
    """Build test app and AsyncClient with in-memory database."""
    owner_a = uuid.UUID("00000000-0000-0000-0000-000000000001")
    owner_b = uuid.UUID("00000000-0000-0000-0000-000000000002")

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    fake_embeddings = FakeEmbeddingProvider(dimension=1024)
    fake_reranker = FakeRerankerProvider()

    async def override_get_session() -> AsyncIterator[AsyncSession]:
        async with session_maker() as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_embedding_provider] = lambda: fake_embeddings
    app.dependency_overrides[get_reranker_provider] = lambda: fake_reranker

    def override_settings() -> Settings:
        cfg = get_settings()
        cfg.app.env = "test"
        cfg.dev_auth.auth_enabled = True
        cfg.dev_auth.user_id = owner_a
        cfg.embedding.provider = "fake"
        cfg.embedding.reranker_provider = "fake"
        return cfg

    app.dependency_overrides[get_settings] = override_settings

    transport = httpx.ASGITransport(app=app)
    async with (
        httpx.AsyncClient(transport=transport, base_url="http://test") as client,
        session_maker() as session,
    ):
        chunk_repo = ChunkRepository(session)
        yield app, client, session, chunk_repo, owner_a, owner_b

    await engine.dispose()
    app.dependency_overrides.clear()


async def _seed_test_corpus(
    session: AsyncSession,
    chunk_repo: ChunkRepository,
    fake_embeddings: FakeEmbeddingProvider,
    owner_id: UUID,
) -> tuple[UUID, UUID, UUID, UUID]:
    """Populate database with sample documents for testing retrieval fusion and filtering."""
    kb_repo = KnowledgeBaseRepository(session)
    doc_repo = DocumentRepository(session)

    # KB 1: Technical specs
    kb1 = await kb_repo.create(owner_id=owner_id, name="Technical Docs", description="Architecture")
    kb1_id = kb1.id
    # KB 2: Company policies
    kb2 = await kb_repo.create(owner_id=owner_id, name="HR Policies", description="Internal rules")
    kb2_id = kb2.id

    # Document 1 (Markdown, KB1): Architecture doc
    doc1, ver1, _ = await doc_repo.create_document_with_version_and_job(
        owner_id=owner_id,
        knowledge_base_id=kb1_id,
        filename="architecture.md",
        content_type="text/markdown",
        file_size_bytes=1000,
        checksum_sha256="sha-arch-001",
        storage_key="kb1/architecture.md",
    )
    doc1_id = doc1.id
    ver1_id = ver1.id
    doc1.created_at = datetime(2026, 1, 1, tzinfo=UTC)
    # Set document status to indexed
    await doc_repo.update_document_status(
        owner_id=owner_id, doc_id=doc1_id, status=DocumentStatus.INDEXED.value
    )

    # Document 2 (PDF, KB1): Incident and troubleshooting guide
    doc2, ver2, _ = await doc_repo.create_document_with_version_and_job(
        owner_id=owner_id,
        knowledge_base_id=kb1_id,
        filename="troubleshooting.pdf",
        content_type="application/pdf",
        file_size_bytes=2000,
        checksum_sha256="sha-trouble-002",
        storage_key="kb1/troubleshooting.pdf",
    )
    doc2_id = doc2.id
    ver2_id = ver2.id
    doc2.created_at = datetime(2026, 1, 10, tzinfo=UTC)
    await doc_repo.update_document_status(
        owner_id=owner_id, doc_id=doc2_id, status=DocumentStatus.INDEXED.value
    )

    # Document 3 (Text, KB2): Employee handbook
    doc3, ver3, _ = await doc_repo.create_document_with_version_and_job(
        owner_id=owner_id,
        knowledge_base_id=kb2_id,
        filename="handbook.txt",
        content_type="text/plain",
        file_size_bytes=500,
        checksum_sha256="sha-handbook-003",
        storage_key="kb2/handbook.txt",
    )
    doc3_id = doc3.id
    ver3_id = ver3.id
    doc3.created_at = datetime(2026, 2, 1, tzinfo=UTC)
    await doc_repo.update_document_status(
        owner_id=owner_id, doc_id=doc3_id, status=DocumentStatus.INDEXED.value
    )

    # Ingest chunks
    content_arch = "Kiến trúc hệ thống RAG phân tán sử dụng pgvector và full-text search."
    emb_arch = await fake_embeddings.embed_query(content_arch)
    await chunk_repo.replace_document_chunks_transactionally(
        owner_id=owner_id,
        document_id=doc1_id,
        document_version_id=ver1_id,
        chunks_data=[
            ChunkCreateData(
                chunk_index=0,
                content=content_arch,
                token_count=20,
                metadata_json={"filename": "architecture.md", "section_header": "Architecture"},
                embedding=emb_arch,
            )
        ],
    )

    content_trouble = "Gặp mã lỗi ERR_CIRCUIT_BREAKER_9012 khi kết nối database timeout."
    emb_trouble = await fake_embeddings.embed_query(content_trouble)
    await chunk_repo.replace_document_chunks_transactionally(
        owner_id=owner_id,
        document_id=doc2_id,
        document_version_id=ver2_id,
        chunks_data=[
            ChunkCreateData(
                chunk_index=0,
                content=content_trouble,
                token_count=18,
                metadata_json={
                    "filename": "troubleshooting.pdf",
                    "page_number": 4,
                    "section_header": "Troubleshooting",
                },
                embedding=emb_trouble,
            )
        ],
    )

    content_hr = "Quy định về thời gian làm việc và chế độ nghỉ phép nhân viên."
    emb_hr = await fake_embeddings.embed_query(content_hr)
    await chunk_repo.replace_document_chunks_transactionally(
        owner_id=owner_id,
        document_id=doc3_id,
        document_version_id=ver3_id,
        chunks_data=[
            ChunkCreateData(
                chunk_index=0,
                content=content_hr,
                token_count=16,
                metadata_json={"filename": "handbook.txt", "section_header": "HR"},
                embedding=emb_hr,
            )
        ],
    )

    await session.commit()
    return kb1_id, kb2_id, doc1_id, doc2_id


# -------------------------------------------------------------------------
# Hybrid Retrieval Integration Tests
# -------------------------------------------------------------------------


async def test_hybrid_retrieval_combines_vector_and_keyword(retrieval_env) -> None:
    session, chunk_repo, _, service, fake_embeddings, owner_a, _ = retrieval_env
    await _seed_test_corpus(session, chunk_repo, fake_embeddings, owner_a)

    # 1. Exact keyword search for specific error code
    res_kw = await service.search(
        owner_id=owner_a,
        query="ERR_CIRCUIT_BREAKER_9012",
        method=RetrievalMethod.KEYWORD,
    )
    assert res_kw.total_results >= 1
    assert "ERR_CIRCUIT_BREAKER_9012" in res_kw.results[0].content
    assert res_kw.results[0].retrieval_method == RetrievalMethod.KEYWORD

    # 2. Semantic vector search for architecture concepts
    res_vec = await service.search(
        owner_id=owner_a,
        query="Kiến trúc hệ thống RAG phân tán",
        method=RetrievalMethod.VECTOR,
    )
    assert res_vec.total_results >= 1
    assert "Kiến trúc hệ thống" in res_vec.results[0].content
    assert res_vec.results[0].retrieval_method == RetrievalMethod.VECTOR

    # 3. Hybrid search returns both semantic and lexical hits
    res_hybrid = await service.search(
        owner_id=owner_a,
        query="Kiến trúc database ERR_CIRCUIT_BREAKER_9012",
        method=RetrievalMethod.HYBRID,
    )
    assert res_hybrid.total_results >= 2
    contents = [r.content for r in res_hybrid.results]
    assert any("ERR_CIRCUIT_BREAKER_9012" in c for c in contents)
    assert any("Kiến trúc hệ thống" in c for c in contents)

    # Context bundle is assembled and source-labeled
    assert res_hybrid.context_bundle is not None
    assert len(res_hybrid.context_bundle.cited_chunks) >= 2
    assert "[S1]" in res_hybrid.context_bundle.context_text
    assert "[S2]" in res_hybrid.context_bundle.context_text
    assert res_hybrid.context_bundle.total_tokens <= 4000


async def test_retrieval_metadata_filtering(retrieval_env) -> None:
    session, chunk_repo, _, service, fake_embeddings, owner_a, _ = retrieval_env
    kb1_id, kb2_id, doc1_id, _ = await _seed_test_corpus(
        session, chunk_repo, fake_embeddings, owner_a
    )

    # Filter by knowledge_base_id = KB1 (Technical Docs)
    res_kb1 = await service.search(
        owner_id=owner_a,
        query="hệ thống",
        filter=RetrievalFilter(knowledge_base_id=kb1_id),
    )
    for r in res_kb1.results:
        assert "handbook.txt" not in r.filename

    # Filter by knowledge_base_id = KB2 (HR Policies)
    res_kb2 = await service.search(
        owner_id=owner_a,
        query="nhân viên",
        filter=RetrievalFilter(knowledge_base_id=kb2_id),
    )
    assert res_kb2.total_results == 1
    assert res_kb2.results[0].filename == "handbook.txt"

    # Filter by specific document_ids
    res_doc = await service.search(
        owner_id=owner_a,
        query="hệ thống database",
        filter=RetrievalFilter(document_ids=[doc1_id]),
    )
    assert res_doc.total_results == 1
    assert res_doc.results[0].document_id == doc1_id

    # Filter by mime_types
    res_pdf = await service.search(
        owner_id=owner_a,
        query="database",
        filter=RetrievalFilter(mime_types=["application/pdf"]),
    )
    assert res_pdf.total_results == 1
    assert res_pdf.results[0].filename == "troubleshooting.pdf"

    # Filter by indexed metadata fields without leaking internal metadata key names
    res_page = await service.search(
        owner_id=owner_a,
        query="database timeout",
        filter=RetrievalFilter(page=4),
    )
    assert res_page.total_results == 1
    assert res_page.results[0].filename == "troubleshooting.pdf"

    res_section = await service.search(
        owner_id=owner_a,
        query="database timeout",
        filter=RetrievalFilter(section="Troubleshooting"),
    )
    assert res_section.total_results == 1
    assert res_section.results[0].section == "Troubleshooting"

    res_created_after = await service.search(
        owner_id=owner_a,
        query="database",
        method=RetrievalMethod.KEYWORD,
        filter=RetrievalFilter(created_after=datetime(2026, 1, 5, tzinfo=UTC)),
    )
    assert res_created_after.total_results == 1
    assert res_created_after.results[0].filename == "troubleshooting.pdf"

    res_created_before = await service.search(
        owner_id=owner_a,
        query="hệ thống",
        method=RetrievalMethod.KEYWORD,
        filter=RetrievalFilter(created_before=datetime(2026, 1, 2, tzinfo=UTC)),
    )
    assert res_created_before.total_results == 1
    assert res_created_before.results[0].filename == "architecture.md"


async def test_retrieval_excludes_non_indexed_and_stale_version_chunks(retrieval_env) -> None:
    session, chunk_repo, _, service, fake_embeddings, owner_a, _ = retrieval_env
    kb1_id, _, doc1_id, _ = await _seed_test_corpus(session, chunk_repo, fake_embeddings, owner_a)
    doc_repo = DocumentRepository(session)

    draft_doc, draft_version, _ = await doc_repo.create_document_with_version_and_job(
        owner_id=owner_a,
        knowledge_base_id=kb1_id,
        filename="draft.txt",
        content_type="text/plain",
        file_size_bytes=100,
        checksum_sha256="sha-draft-004",
        storage_key="kb1/draft.txt",
    )
    draft_embedding = await fake_embeddings.embed_query("DRAFT_SECRET_KEYWORD_777")
    await chunk_repo.replace_document_chunks_transactionally(
        owner_id=owner_a,
        document_id=draft_doc.id,
        document_version_id=draft_version.id,
        chunks_data=[
            ChunkCreateData(
                chunk_index=0,
                content="DRAFT_SECRET_KEYWORD_777 must not appear before indexing.",
                token_count=8,
                metadata_json={"filename": "draft.txt", "section_header": "Draft"},
                embedding=draft_embedding,
            )
        ],
    )

    indexed_doc = await doc_repo.get_document_by_id(owner_id=owner_a, doc_id=doc1_id)
    assert indexed_doc is not None
    stale_version = DocumentVersionModel(
        id=uuid.uuid4(),
        owner_id=owner_a,
        document_id=doc1_id,
        version_number=2,
        file_size_bytes=101,
        checksum_sha256="sha-stale-005",
        storage_key="kb1/stale.txt",
        mime_type="text/plain",
    )
    session.add(stale_version)
    await session.flush()
    indexed_doc.current_version_id = stale_version.id
    stale_embedding = await fake_embeddings.embed_query("STALE_VERSION_KEYWORD_888")
    await chunk_repo.replace_document_chunks_transactionally(
        owner_id=owner_a,
        document_id=doc1_id,
        document_version_id=stale_version.id,
        chunks_data=[
            ChunkCreateData(
                chunk_index=0,
                content="current version text without stale keyword",
                token_count=7,
                metadata_json={"filename": "architecture.md", "section_header": "Architecture"},
                embedding=stale_embedding,
            )
        ],
    )
    await session.commit()

    draft_res = await service.search(
        owner_id=owner_a,
        query="DRAFT_SECRET_KEYWORD_777",
        method=RetrievalMethod.KEYWORD,
    )
    assert draft_res.total_results == 0

    stale_res = await service.search(
        owner_id=owner_a,
        query="Kiến trúc hệ thống",
        method=RetrievalMethod.KEYWORD,
    )
    assert all("Kiến trúc hệ thống" not in result.content for result in stale_res.results)


async def test_retrieval_tenant_isolation(retrieval_env) -> None:
    session, chunk_repo, _, service, fake_embeddings, owner_a, owner_b = retrieval_env
    await _seed_test_corpus(session, chunk_repo, fake_embeddings, owner_a)

    # Owner B searching for Owner A's documents must receive 0 results
    res_owner_b = await service.search(
        owner_id=owner_b,
        query="Kiến trúc hệ thống RAG",
        method=RetrievalMethod.HYBRID,
    )
    assert res_owner_b.total_results == 0
    assert len(res_owner_b.results) == 0
    assert res_owner_b.context_bundle is not None
    assert res_owner_b.context_bundle.total_chunks == 0


async def test_retrieval_query_audit_logging(retrieval_env) -> None:
    reset_retrieval_metrics()
    session, chunk_repo, rag_query_repo, service, fake_embeddings, owner_a, _ = retrieval_env
    await _seed_test_corpus(session, chunk_repo, fake_embeddings, owner_a)

    res = await service.search(
        owner_id=owner_a,
        query="truy vấn kiểm thử audit log",
        method=RetrievalMethod.HYBRID,
    )
    await session.commit()

    # Query events are persisted in rag_queries table
    logged_queries = await rag_query_repo.get_queries_by_owner(owner_id=owner_a, limit=10)
    assert len(logged_queries) >= 1
    assert logged_queries[0].query_text == "truy vấn kiểm thử audit log"
    assert logged_queries[0].retrieval_method == "hybrid"
    assert logged_queries[0].result_count == res.total_results
    assert logged_queries[0].stage_latencies_ms["vector"] >= 0.0
    assert logged_queries[0].stage_latencies_ms["keyword"] >= 0.0
    assert logged_queries[0].stage_latencies_ms["fusion"] >= 0.0
    assert logged_queries[0].stage_latencies_ms["rerank"] >= 0.0
    assert logged_queries[0].stage_latencies_ms["context"] >= 0.0

    query_metrics = RETRIEVAL_QUERY_TOTAL.snapshot()
    assert query_metrics[(("method", "hybrid"),)] == 1.0

    stage_metrics = RETRIEVAL_STAGE_LATENCY_MS.snapshot()
    for stage in ("normalize", "vector", "keyword", "fusion", "rerank", "context", "total"):
        sample = stage_metrics[(("stage", stage),)]
        assert sample.count == 1
        assert sample.total >= 0.0


async def test_reranker_can_be_disabled(retrieval_env) -> None:
    session, chunk_repo, rag_query_repo, _, fake_embeddings, owner_a, _ = retrieval_env
    await _seed_test_corpus(session, chunk_repo, fake_embeddings, owner_a)

    # RetrievalService with NullRerankerProvider (disabled reranker)
    null_reranker = NullRerankerProvider()
    service_no_rerank = RetrievalService(
        chunk_repo=chunk_repo,
        rag_query_repo=rag_query_repo,
        embedding_provider=fake_embeddings,
        reranker_provider=null_reranker,
    )

    res = await service_no_rerank.search(
        owner_id=owner_a,
        query="Kiến trúc hệ thống",
        method=RetrievalMethod.HYBRID,
    )
    assert res.total_results >= 1


# -------------------------------------------------------------------------
# REST API Endpoint Tests (POST /api/v1/retrieval/search)
# -------------------------------------------------------------------------


async def test_api_search_endpoint_success(api_env) -> None:
    _, client, session, chunk_repo, owner_a, _ = api_env
    fake_embeddings = FakeEmbeddingProvider(dimension=1024)
    kb1_id, _, _, _ = await _seed_test_corpus(session, chunk_repo, fake_embeddings, owner_a)

    payload = {
        "query": "Kiến trúc RAG pgvector",
        "method": "hybrid",
        "filter": {
            "knowledge_base_id": str(kb1_id),
            "section": "Architecture",
        },
        "include_context_bundle": True,
    }

    resp = await client.post(
        "/api/v1/retrieval/search",
        json=payload,
        headers={"x-user-id": str(owner_a)},
    )
    assert resp.status_code == 200
    data = resp.json()

    assert data["query"] == "Kiến trúc RAG pgvector"
    assert data["retrieval_method"] == "hybrid"
    assert data["total_results"] >= 1
    assert len(data["results"]) >= 1

    first_hit = data["results"][0]
    assert "chunk_id" in first_hit
    assert "document_id" in first_hit
    assert "content" in first_hit
    assert "score" in first_hit
    assert "retrieval_method" in first_hit
    assert "filename" in first_hit

    # Context bundle check
    assert data["context_bundle"] is not None
    assert "[S1]" in data["context_bundle"]["context_text"]
    assert len(data["context_bundle"]["cited_chunks"]) >= 1
    assert data["context_bundle"]["total_tokens"] > 0
    assert data["stage_latencies_ms"]["vector"] >= 0.0
    assert data["stage_latencies_ms"]["keyword"] >= 0.0


async def test_api_search_endpoint_unauthorized(api_env) -> None:
    app, client, _, _, _, _ = api_env

    # Disable dev auth to verify fail closed behavior
    def override_settings_no_auth() -> Settings:
        cfg = get_settings()
        cfg.dev_auth.auth_enabled = False
        return cfg

    app.dependency_overrides[get_settings] = override_settings_no_auth

    resp = await client.post(
        "/api/v1/retrieval/search",
        json={"query": "test query"},
    )
    assert resp.status_code == 401
    data = resp.json()
    assert "error" in data
    assert data["error"]["code"] == "UNAUTHORIZED"
