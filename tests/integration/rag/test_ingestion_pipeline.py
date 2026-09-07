"""Integration tests for the end-to-end RAG Ingestion Pipeline."""

from __future__ import annotations

import io
import uuid
from collections.abc import AsyncIterator
from typing import BinaryIO
from uuid import UUID

import pytest
from pypdf import PdfWriter
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import rag_llm_services_api.db.models  # noqa: F401
from rag_llm_services_api.application.ingestion_pipeline import IngestionPipeline
from rag_llm_services_api.db.base import Base
from rag_llm_services_api.domain.documents import DocumentStatus, IngestionJobStatus
from rag_llm_services_api.infrastructure.repositories.chunks import ChunkRepository
from rag_llm_services_api.infrastructure.repositories.documents import DocumentRepository
from rag_llm_services_api.infrastructure.repositories.knowledge_bases import KnowledgeBaseRepository
from rag_llm_services_api.infrastructure.storage.base import ObjectStoragePort
from rag_llm_services_embeddings.fake import FakeEmbeddingProvider
from rag_llm_services_rag.chunking import Chunker
from rag_llm_services_rag.normalization import TextNormalizer
from rag_llm_services_rag.parsers.registry import get_default_parser_registry
from rag_llm_services_shared.errors import NotFoundError


class InMemoryObjectStorage(ObjectStoragePort):
    """In-memory object storage stand-in for integration tests."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    async def put_object(
        self,
        object_key: str,
        data: bytes | BinaryIO,
        length: int,
        content_type: str,
    ) -> None:
        if isinstance(data, bytes):
            self.objects[object_key] = data
        else:
            self.objects[object_key] = data.read()

    async def get_object(self, object_key: str) -> bytes:
        if object_key not in self.objects:
            raise NotFoundError(f"Storage object '{object_key}' not found")
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
async def pipeline_env() -> AsyncIterator[
    tuple[
        AsyncSession,
        InMemoryObjectStorage,
        DocumentRepository,
        ChunkRepository,
        IngestionPipeline,
        UUID,
        UUID,
    ]
]:
    """Build isolated in-memory SQLite database, fake storage, and IngestionPipeline."""
    owner_a = uuid.UUID("00000000-0000-0000-0000-000000000001")
    owner_b = uuid.UUID("00000000-0000-0000-0000-000000000002")

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(engine, expire_on_commit=False)

    storage = InMemoryObjectStorage()
    fake_embeddings = FakeEmbeddingProvider(dimension=1024)
    parser_registry = get_default_parser_registry()
    normalizer = TextNormalizer()
    chunker = Chunker(chunk_size=30, chunk_overlap=5)

    async with session_maker() as session:
        doc_repo = DocumentRepository(session)
        chunk_repo = ChunkRepository(session)
        pipeline = IngestionPipeline(
            object_storage=storage,
            document_repo=doc_repo,
            chunk_repo=chunk_repo,
            embedding_provider=fake_embeddings,
            parser_registry=parser_registry,
            normalizer=normalizer,
            chunker=chunker,
        )

        yield session, storage, doc_repo, chunk_repo, pipeline, owner_a, owner_b

    await engine.dispose()


# -----------------------------------------------------------------------------
# End-to-End Ingestion Pipeline Tests
# -----------------------------------------------------------------------------


async def test_ingest_markdown_vietnamese_end_to_end(pipeline_env) -> None:
    session, storage, doc_repo, chunk_repo, pipeline, owner_a, _ = pipeline_env
    kb_repo = KnowledgeBaseRepository(session)

    # 1. Setup KB and Document
    kb = await kb_repo.create(
        owner_id=owner_a,
        name="Tài liệu kỹ thuật",
        description="Kiến trúc hệ thống RAG",
    )

    md_content = """# Kiến trúc hệ thống RAG
Dự án nền tảng RAG LLM Services cung cấp khả năng tìm kiếm ngữ nghĩa tiếng Việt.

## Thành phần Embedding
Sử dụng mô hình BGE-M3 với chiều vector 1024 dense.

## Thành phần Chunker
Phân đoạn văn bản đệ quy bảo toàn ngữ cảnh và cấu trúc tiêu đề.
""".encode()

    storage_key = f"knowledge_bases/{kb.id}/docs/arch.md"
    await storage.put_object(storage_key, md_content, len(md_content), "text/markdown")

    doc, version, job = await doc_repo.create_document_with_version_and_job(
        owner_id=owner_a,
        knowledge_base_id=kb.id,
        filename="arch.md",
        content_type="text/markdown",
        file_size_bytes=len(md_content),
        checksum_sha256="dummy-checksum-1",
        storage_key=storage_key,
    )
    await session.commit()

    # 2. Run ingestion
    result = await pipeline.ingest_document(
        owner_id=owner_a,
        document_id=doc.id,
        version_id=version.id,
        job_id=job.id,
    )
    await session.commit()

    # 3. Verify result status
    assert result.status == DocumentStatus.INDEXED
    assert result.chunk_count > 0
    assert result.error_message is None

    # 4. Verify document and job status updated in database
    refreshed_doc = await doc_repo.get_document_by_id(owner_a, doc.id)
    assert refreshed_doc is not None
    assert refreshed_doc.status == DocumentStatus.INDEXED.value
    assert refreshed_doc.error_message is None

    refreshed_job = await doc_repo.get_ingestion_job(owner_a, job.id)
    assert refreshed_job is not None
    assert refreshed_job.status == IngestionJobStatus.INDEXED.value

    # 5. Verify persisted chunks and pgvector embeddings
    chunks = await chunk_repo.get_chunks_by_version(owner_a, version.id)
    assert len(chunks) == result.chunk_count

    for chunk in chunks:
        assert chunk.owner_id == owner_a
        assert chunk.document_id == doc.id
        assert chunk.document_version_id == version.id
        assert chunk.token_count > 0
        assert chunk.content != ""
        # 1024-dim dense embedding
        assert chunk.embedding is not None
        assert len(chunk.embedding) == 1024
        # Metadata checks
        assert "filename" in chunk.metadata_json
        assert chunk.metadata_json["filename"] == "arch.md"


async def test_idempotent_reindexing_does_not_duplicate_chunks(pipeline_env) -> None:
    session, storage, doc_repo, chunk_repo, pipeline, owner_a, _ = pipeline_env
    kb_repo = KnowledgeBaseRepository(session)

    kb = await kb_repo.create(owner_id=owner_a, name="Reindex KB")
    text_content = "Đoạn văn kiểm thử tính lũy thừa (idempotency) của việc đánh chỉ mục.".encode()
    storage_key = f"knowledge_bases/{kb.id}/docs/reindex.txt"
    await storage.put_object(storage_key, text_content, len(text_content), "text/plain")

    doc, version, job = await doc_repo.create_document_with_version_and_job(
        owner_id=owner_a,
        knowledge_base_id=kb.id,
        filename="reindex.txt",
        content_type="text/plain",
        file_size_bytes=len(text_content),
        checksum_sha256="reindex-checksum",
        storage_key=storage_key,
    )
    doc_id = doc.id
    ver_id = version.id
    job_id = job.id
    await session.commit()

    # First ingestion run
    res1 = await pipeline.ingest_document(owner_a, doc_id, ver_id, job_id)
    await session.commit()
    count_1 = await chunk_repo.count_chunks_by_version(owner_a, ver_id)
    assert count_1 == res1.chunk_count

    # Second ingestion run (reindex retry)
    res2 = await pipeline.ingest_document(owner_a, doc_id, ver_id, job_id)
    await session.commit()
    count_2 = await chunk_repo.count_chunks_by_version(owner_a, ver_id)

    # Idempotency guarantee: count must NOT double
    assert count_2 == count_1
    assert res2.chunk_count == res1.chunk_count


async def test_ingest_pdf_document(pipeline_env) -> None:
    session, storage, doc_repo, _chunk_repo, pipeline, owner_a, _ = pipeline_env
    kb_repo = KnowledgeBaseRepository(session)

    kb = await kb_repo.create(owner_id=owner_a, name="PDF KB")

    writer = PdfWriter()
    writer.add_blank_page(150, 150)
    writer.add_blank_page(150, 150)
    buf = io.BytesIO()
    writer.write(buf)
    pdf_bytes = buf.getvalue()

    storage_key = f"knowledge_bases/{kb.id}/docs/doc.pdf"
    await storage.put_object(storage_key, pdf_bytes, len(pdf_bytes), "application/pdf")

    doc, version, job = await doc_repo.create_document_with_version_and_job(
        owner_id=owner_a,
        knowledge_base_id=kb.id,
        filename="doc.pdf",
        content_type="application/pdf",
        file_size_bytes=len(pdf_bytes),
        checksum_sha256="pdf-checksum",
        storage_key=storage_key,
    )
    await session.commit()

    res = await pipeline.ingest_document(owner_a, doc.id, version.id, job.id)
    await session.commit()
    assert res.status == DocumentStatus.INDEXED


async def test_ingestion_failure_records_error_and_failed_status(pipeline_env) -> None:
    session, _storage, doc_repo, _, pipeline, owner_a, _ = pipeline_env
    kb_repo = KnowledgeBaseRepository(session)

    kb = await kb_repo.create(owner_id=owner_a, name="Failure KB")

    # Storage key points to a missing object in storage
    missing_key = f"knowledge_bases/{kb.id}/docs/missing.pdf"

    doc, version, job = await doc_repo.create_document_with_version_and_job(
        owner_id=owner_a,
        knowledge_base_id=kb.id,
        filename="missing.pdf",
        content_type="application/pdf",
        file_size_bytes=100,
        checksum_sha256="missing-checksum",
        storage_key=missing_key,
    )
    await session.commit()

    # Ingest document where file does not exist in storage
    result = await pipeline.ingest_document(owner_a, doc.id, version.id, job.id)
    await session.commit()

    # Pipeline gracefully captures error and marks FAILED
    assert result.status == DocumentStatus.FAILED
    assert result.error_message is not None
    assert "not found" in result.error_message.lower()

    # DB records reflect FAILED status
    refreshed_doc = await doc_repo.get_document_by_id(owner_a, doc.id)
    assert refreshed_doc is not None
    assert refreshed_doc.status == DocumentStatus.FAILED.value
    assert refreshed_doc.error_message is not None

    refreshed_job = await doc_repo.get_ingestion_job(owner_a, job.id)
    assert refreshed_job is not None
    assert refreshed_job.status == IngestionJobStatus.FAILED.value


async def test_ingestion_tenant_isolation(pipeline_env) -> None:
    session, storage, doc_repo, _, pipeline, owner_a, owner_b = pipeline_env
    kb_repo = KnowledgeBaseRepository(session)

    kb = await kb_repo.create(owner_id=owner_a, name="Owner A KB")
    content = b"Owner A confidential technical document"
    storage_key = f"knowledge_bases/{kb.id}/docs/confidential.txt"
    await storage.put_object(storage_key, content, len(content), "text/plain")

    doc, version, _ = await doc_repo.create_document_with_version_and_job(
        owner_id=owner_a,
        knowledge_base_id=kb.id,
        filename="confidential.txt",
        content_type="text/plain",
        file_size_bytes=len(content),
        checksum_sha256="confidential-hash",
        storage_key=storage_key,
    )
    await session.commit()

    # Owner B attempting to ingest Owner A's document must fail with NotFoundError
    with pytest.raises(NotFoundError):
        await pipeline.ingest_document(owner_id=owner_b, document_id=doc.id, version_id=version.id)
