"""Integration tests for the asynchronous ingestion worker task."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import BinaryIO

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import rag_llm_services_api.db.models  # noqa: F401
from rag_llm_services_api.core.config import Settings
from rag_llm_services_api.core.errors import NotFoundError
from rag_llm_services_api.db.base import Base
from rag_llm_services_api.domain.documents import DocumentStatus, IngestionJobStatus
from rag_llm_services_api.infrastructure.queue.base import IngestionTaskPayload
from rag_llm_services_api.infrastructure.repositories.chunks import ChunkRepository
from rag_llm_services_api.infrastructure.repositories.documents import DocumentRepository
from rag_llm_services_api.infrastructure.repositories.knowledge_bases import KnowledgeBaseRepository
from rag_llm_services_api.infrastructure.storage.base import ObjectStoragePort
from rag_llm_services_embeddings.fake import FakeEmbeddingProvider
from rag_llm_services_worker.tasks import RetryableIngestionError, run_ingestion_task_once


class InMemoryObjectStorage(ObjectStoragePort):
    """In-memory object storage stand-in for worker integration tests."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    async def put_object(
        self,
        object_key: str,
        data: bytes | BinaryIO,
        length: int,
        content_type: str,
    ) -> None:
        del length, content_type
        self.objects[object_key] = data if isinstance(data, bytes) else data.read()

    async def get_object(self, object_key: str) -> bytes:
        if object_key not in self.objects:
            raise NotFoundError("Storage object not found")
        return self.objects[object_key]

    async def get_object_stream(
        self, object_key: str, chunk_size: int = 65536
    ) -> AsyncIterator[bytes]:
        raw = await self.get_object(object_key)
        for i in range(0, len(raw), chunk_size):
            yield raw[i : i + chunk_size]

    async def delete_object(self, object_key: str) -> None:
        self.objects.pop(object_key, None)

    async def object_exists(self, object_key: str) -> bool:
        return object_key in self.objects

    async def ensure_bucket_exists(self) -> None:
        pass


@pytest.fixture
async def worker_env() -> AsyncIterator[
    tuple[async_sessionmaker[AsyncSession], InMemoryObjectStorage, Settings, uuid.UUID]
]:
    """Build isolated database, fake storage, and worker dependencies."""
    owner_id = uuid.UUID("00000000-0000-0000-0000-000000000001")
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    storage = InMemoryObjectStorage()
    settings = Settings(_env_file=None)
    settings.app.env = "test"
    settings.embedding.provider = "fake"

    yield session_maker, storage, settings, owner_id

    await engine.dispose()


async def _seed_document(
    *,
    session_maker: async_sessionmaker[AsyncSession],
    storage: InMemoryObjectStorage,
    owner_id: uuid.UUID,
    content: bytes,
    store_object: bool = True,
) -> IngestionTaskPayload:
    async with session_maker() as session:
        kb_repo = KnowledgeBaseRepository(session)
        doc_repo = DocumentRepository(session)

        kb = await kb_repo.create(owner_id=owner_id, name="Worker KB")
        storage_key = f"knowledge_bases/{kb.id}/documents/worker.txt"
        if store_object:
            await storage.put_object(storage_key, content, len(content), "text/plain")
        doc, version, job = await doc_repo.create_document_with_version_and_job(
            owner_id=owner_id,
            knowledge_base_id=kb.id,
            filename="worker.txt",
            content_type="text/plain",
            file_size_bytes=len(content),
            checksum_sha256=f"checksum-{job_suffix()}",
            storage_key=storage_key,
        )
        await session.commit()
        return IngestionTaskPayload(
            owner_id=owner_id,
            job_id=job.id,
            document_id=doc.id,
            version_id=version.id,
        )


def job_suffix() -> str:
    """Return a unique checksum suffix for test rows."""
    return uuid.uuid4().hex


async def test_worker_indexes_document_and_skips_duplicate_task(worker_env) -> None:
    session_maker, storage, settings, owner_id = worker_env
    payload = await _seed_document(
        session_maker=session_maker,
        storage=storage,
        owner_id=owner_id,
        content=b"Async worker indexing keeps ingestion outside the API request path.",
    )

    first = await run_ingestion_task_once(
        payload,
        settings=settings,
        session_maker=session_maker,
        object_storage=storage,
        embedding_provider=FakeEmbeddingProvider(dimension=1024),
    )

    assert first.status == DocumentStatus.INDEXED.value
    assert first.chunk_count > 0
    assert first.attempt_count == 1

    async with session_maker() as session:
        doc_repo = DocumentRepository(session)
        chunk_repo = ChunkRepository(session)
        job = await doc_repo.get_ingestion_job(owner_id, payload.job_id)
        assert job is not None
        assert job.status == IngestionJobStatus.INDEXED.value
        assert job.attempt_count == 1
        assert job.queued_task_id == payload.task_id
        initial_chunk_count = await chunk_repo.count_chunks_by_version(
            owner_id,
            payload.version_id,
        )

    second = await run_ingestion_task_once(
        payload,
        settings=settings,
        session_maker=session_maker,
        object_storage=storage,
        embedding_provider=FakeEmbeddingProvider(dimension=1024),
    )

    assert second.status == "SKIPPED"
    assert second.attempt_count == 1
    assert second.chunk_count == initial_chunk_count

    async with session_maker() as session:
        chunk_repo = ChunkRepository(session)
        assert await chunk_repo.count_chunks_by_version(owner_id, payload.version_id) == (
            initial_chunk_count
        )


async def test_worker_failed_ingestion_records_safe_error(worker_env) -> None:
    session_maker, storage, settings, owner_id = worker_env
    payload = await _seed_document(
        session_maker=session_maker,
        storage=storage,
        owner_id=owner_id,
        content=b"missing backing object",
        store_object=False,
    )

    result = await run_ingestion_task_once(
        payload,
        settings=settings,
        session_maker=session_maker,
        object_storage=storage,
        embedding_provider=FakeEmbeddingProvider(dimension=1024),
    )

    assert result.status == DocumentStatus.FAILED.value
    assert result.error_message is not None
    assert "not found" in result.error_message.lower()
    assert str(payload.version_id) not in result.error_message

    async with session_maker() as session:
        doc_repo = DocumentRepository(session)
        job = await doc_repo.get_ingestion_job(owner_id, payload.job_id)
        doc = await doc_repo.get_document_by_id(owner_id, payload.document_id)
        assert job is not None
        assert doc is not None
        assert job.status == IngestionJobStatus.FAILED.value
        assert job.attempt_count == 1
        assert job.error_message == result.error_message
        assert doc.status == DocumentStatus.FAILED.value
        assert doc.error_message == result.error_message


async def test_worker_non_final_failure_stays_retryable_until_retry_succeeds(worker_env) -> None:
    session_maker, storage, settings, owner_id = worker_env
    content = b"retryable storage delay eventually indexes"
    payload = await _seed_document(
        session_maker=session_maker,
        storage=storage,
        owner_id=owner_id,
        content=content,
        store_object=False,
    )

    with pytest.raises(RetryableIngestionError):
        await run_ingestion_task_once(
            payload,
            settings=settings,
            session_maker=session_maker,
            object_storage=storage,
            embedding_provider=FakeEmbeddingProvider(dimension=1024),
            final_attempt=False,
            raise_on_failed_result=True,
        )

    async with session_maker() as session:
        doc_repo = DocumentRepository(session)
        job = await doc_repo.get_ingestion_job(owner_id, payload.job_id)
        doc = await doc_repo.get_document_by_id(owner_id, payload.document_id)
        assert job is not None
        assert doc is not None
        assert job.status == IngestionJobStatus.PROCESSING.value
        assert doc.status == DocumentStatus.PROCESSING.value
        assert job.attempt_count == 1

    async with session_maker() as session:
        doc_repo = DocumentRepository(session)
        doc = await doc_repo.get_document_by_id(owner_id, payload.document_id)
        assert doc is not None
        version = next(v for v in doc.versions if v.id == payload.version_id)
        await storage.put_object(version.storage_key, content, len(content), "text/plain")

    result = await run_ingestion_task_once(
        payload,
        settings=settings,
        session_maker=session_maker,
        object_storage=storage,
        embedding_provider=FakeEmbeddingProvider(dimension=1024),
    )

    assert result.status == DocumentStatus.INDEXED.value
    assert result.attempt_count == 2
