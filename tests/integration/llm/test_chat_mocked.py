"""Mocked chat integration tests for local conversation memory and citations."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from uuid import UUID

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import rag_llm_services_api.db.models  # noqa: F401
from rag_llm_services_api.core.config import Settings, get_settings
from rag_llm_services_api.db.base import Base
from rag_llm_services_api.db.models.conversation import MessageModel
from rag_llm_services_api.db.models.llm_usage import LLMUsageModel
from rag_llm_services_api.db.session import get_session
from rag_llm_services_api.domain.documents import DocumentStatus
from rag_llm_services_api.infrastructure.llm import get_llm_provider
from rag_llm_services_api.infrastructure.repositories.chunks import ChunkCreateData, ChunkRepository
from rag_llm_services_api.infrastructure.repositories.documents import DocumentRepository
from rag_llm_services_api.infrastructure.repositories.knowledge_bases import KnowledgeBaseRepository
from rag_llm_services_api.main import create_app
from rag_llm_services_embeddings.fake import FakeEmbeddingProvider
from rag_llm_services_llm.deepseek import FakeLLMProvider


@pytest.fixture
async def chat_api_env() -> AsyncIterator[
    tuple[FastAPI, httpx.AsyncClient, async_sessionmaker[AsyncSession], UUID]
]:
    """Build test app with in-memory database and fake LLM/embedding providers."""
    owner_id = uuid.UUID("00000000-0000-0000-0000-000000000001")

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(engine, expire_on_commit=False)

    async def override_get_session() -> AsyncIterator[AsyncSession]:
        async with session_maker() as session:
            yield session

    def override_settings() -> Settings:
        cfg = Settings(_env_file=None)
        cfg.app.env = "test"
        cfg.dev_auth.auth_enabled = True
        cfg.dev_auth.user_id = owner_id
        cfg.llm.provider = "fake"
        cfg.embedding.provider = "fake"
        cfg.embedding.reranker_provider = "fake"
        return cfg

    app = create_app()
    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_settings] = override_settings
    app.dependency_overrides[get_llm_provider] = lambda: FakeLLMProvider()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield app, client, session_maker, owner_id

    await engine.dispose()
    app.dependency_overrides.clear()


async def _seed_indexed_source(
    session_maker: async_sessionmaker[AsyncSession],
    owner_id: UUID,
) -> UUID:
    fake_embeddings = FakeEmbeddingProvider(dimension=1024)
    async with session_maker() as session:
        kb_repo = KnowledgeBaseRepository(session)
        doc_repo = DocumentRepository(session)
        chunk_repo = ChunkRepository(session)

        kb = await kb_repo.create(
            owner_id=owner_id,
            name="DeepSeek Notes",
            description="Provider behavior",
        )
        doc, version, _ = await doc_repo.create_document_with_version_and_job(
            owner_id=owner_id,
            knowledge_base_id=kb.id,
            filename="deepseek.md",
            content_type="text/markdown",
            file_size_bytes=512,
            checksum_sha256="sha-chat-001",
            storage_key="kb/deepseek.md",
        )
        doc_id = doc.id
        version_id = version.id
        await doc_repo.update_document_status(
            owner_id=owner_id,
            doc_id=doc_id,
            status=DocumentStatus.INDEXED.value,
        )
        content = "DeepSeek Responses API is stateless, so local chat memory owns continuation."
        embedding = await fake_embeddings.embed_query(content)
        await chunk_repo.replace_document_chunks_transactionally(
            owner_id=owner_id,
            document_id=doc_id,
            document_version_id=version_id,
            chunks_data=[
                ChunkCreateData(
                    chunk_index=0,
                    content=content,
                    token_count=12,
                    metadata_json={"filename": "deepseek.md", "section_header": "Provider"},
                    embedding=embedding,
                )
            ],
        )
        await session.commit()
        return kb.id


async def test_chat_endpoint_returns_grounded_mocked_answer_and_persists_state(
    chat_api_env,
) -> None:
    _, client, session_maker, owner_id = chat_api_env
    kb_id = await _seed_indexed_source(session_maker, owner_id)

    response = await client.post(
        "/api/v1/chat",
        json={
            "message": "How should DeepSeek continuation be handled?",
            "knowledge_base_id": str(kb_id),
        },
        headers={"x-user-id": str(owner_id), "x-request-id": "chat-test-req"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["request_id"] == "chat-test-req"
    assert payload["answer"] == "Mocked answer grounded in [S1]."
    assert payload["provider"] == "fake"
    assert payload["usage"]["total_tokens"] > 0
    assert payload["citations"][0]["source_id"] == "[S1]"
    assert payload["retrieved_sources"][0]["filename"] == "deepseek.md"

    async with session_maker() as session:
        messages = list(
            (await session.execute(select(MessageModel).where(MessageModel.owner_id == owner_id)))
            .scalars()
            .all()
        )
        usage_records = list(
            (await session.execute(select(LLMUsageModel).where(LLMUsageModel.owner_id == owner_id)))
            .scalars()
            .all()
        )

    assert [message.role for message in messages] == ["user", "assistant"]
    assert usage_records[0].provider == "fake"
    assert usage_records[0].message_id == messages[1].id


async def test_chat_stream_endpoint_uses_semantic_events_without_done_sentinel(
    chat_api_env,
) -> None:
    _, client, session_maker, owner_id = chat_api_env
    kb_id = await _seed_indexed_source(session_maker, owner_id)

    async with client.stream(
        "POST",
        "/api/v1/chat/stream",
        json={
            "message": "How should DeepSeek continuation be handled?",
            "knowledge_base_id": str(kb_id),
        },
        headers={"x-user-id": str(owner_id)},
    ) as response:
        assert response.status_code == 200
        body = (await response.aread()).decode("utf-8")

    assert "event: response.output_text.delta" in body
    assert "event: response.completed" in body
    assert '"citations": [{"source_id": "[S1]"' in body
    assert '"retrieved_sources": [{"source_id": "[S1]"' in body
    assert '"filename": "deepseek.md"' in body
    assert "[DONE]" not in body
