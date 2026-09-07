"""Integration tests for Knowledge Base and Document Management APIs."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import BinaryIO
from uuid import UUID

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Ensure models are registered on Base.metadata
import rag_llm_services_api.db.models  # noqa: F401
from rag_llm_services_api.core.config import Settings, get_settings
from rag_llm_services_api.core.errors import NotFoundError
from rag_llm_services_api.db.base import Base
from rag_llm_services_api.db.session import get_session
from rag_llm_services_api.infrastructure.storage.base import ObjectStoragePort
from rag_llm_services_api.infrastructure.storage.minio import get_object_storage
from rag_llm_services_api.main import create_app


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
async def test_env() -> AsyncIterator[
    tuple[FastAPI, httpx.AsyncClient, InMemoryObjectStorage, UUID, UUID]
]:
    """Build isolated app, in-memory SQLite database, fake storage, and two tenant identities."""
    owner_a = uuid.UUID("00000000-0000-0000-0000-000000000001")
    owner_b = uuid.UUID("00000000-0000-0000-0000-000000000002")

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(engine, expire_on_commit=False)

    async def override_get_session() -> AsyncIterator[AsyncSession]:
        async with session_maker() as session:
            yield session

    fake_storage = InMemoryObjectStorage()

    app = create_app()
    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_object_storage] = lambda: fake_storage

    # Configure dev auth settings so default requests resolve to owner_a
    def override_settings() -> Settings:
        cfg = get_settings()
        cfg.dev_auth.auth_enabled = True
        cfg.dev_auth.user_id = owner_a
        return cfg

    app.dependency_overrides[get_settings] = override_settings

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield app, client, fake_storage, owner_a, owner_b

    await engine.dispose()
    app.dependency_overrides.clear()


# -------------------------------------------------------------------------
# Knowledge Base CRUD & Tenant Isolation
# -------------------------------------------------------------------------


async def test_knowledge_base_crud(test_env) -> None:
    _, client, _, owner_a, _ = test_env

    # 1. Create KB
    create_resp = await client.post(
        "/api/v1/knowledge-bases",
        json={"name": "Engineering Docs", "description": "Technical specifications"},
    )
    assert create_resp.status_code == 201
    kb = create_resp.json()
    assert kb["name"] == "Engineering Docs"
    assert kb["description"] == "Technical specifications"
    assert kb["owner_id"] == str(owner_a)
    kb_id = kb["id"]

    # 2. Get KB
    get_resp = await client.get(f"/api/v1/knowledge-bases/{kb_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == kb_id

    # 3. List KBs
    list_resp = await client.get("/api/v1/knowledge-bases")
    assert list_resp.status_code == 200
    items = list_resp.json()
    assert len(items) == 1
    assert items[0]["id"] == kb_id

    # 4. Update KB
    update_resp = await client.patch(
        f"/api/v1/knowledge-bases/{kb_id}",
        json={"name": "Updated Docs", "description": "New description"},
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["name"] == "Updated Docs"

    # 5. Delete KB
    del_resp = await client.delete(f"/api/v1/knowledge-bases/{kb_id}")
    assert del_resp.status_code == 204

    # 6. Verify deleted
    get_again = await client.get(f"/api/v1/knowledge-bases/{kb_id}")
    assert get_again.status_code == 404


async def test_knowledge_base_owner_isolation(test_env) -> None:
    _, client, _, _owner_a, owner_b = test_env

    # Owner A creates a KB
    create_resp = await client.post(
        "/api/v1/knowledge-bases",
        json={"name": "Owner A Secret Knowledge"},
    )
    assert create_resp.status_code == 201
    kb_a_id = create_resp.json()["id"]

    # Owner B cannot see Owner A's KB in list
    headers_b = {"X-User-Id": str(owner_b)}
    list_b = await client.get("/api/v1/knowledge-bases", headers=headers_b)
    assert list_b.status_code == 200
    assert len(list_b.json()) == 0

    # Owner B cannot fetch Owner A's KB (404)
    get_b = await client.get(f"/api/v1/knowledge-bases/{kb_a_id}", headers=headers_b)
    assert get_b.status_code == 404
    assert get_b.json()["error"]["code"] == "NOT_FOUND"

    # Owner B cannot update Owner A's KB (404)
    patch_b = await client.patch(
        f"/api/v1/knowledge-bases/{kb_a_id}",
        json={"name": "Hacked Name"},
        headers=headers_b,
    )
    assert patch_b.status_code == 404

    # Owner B cannot delete Owner A's KB (404)
    del_b = await client.delete(f"/api/v1/knowledge-bases/{kb_a_id}", headers=headers_b)
    assert del_b.status_code == 404


# -------------------------------------------------------------------------
# Document Upload & Duplicate Checksum Tests
# -------------------------------------------------------------------------


async def test_document_upload_lifecycle(test_env) -> None:
    _, client, storage, _, _ = test_env

    # 1. Create KB
    kb_resp = await client.post(
        "/api/v1/knowledge-bases",
        json={"name": "Upload Target KB"},
    )
    kb_id = kb_resp.json()["id"]

    # 2. Upload valid PDF
    pdf_content = b"%PDF-1.4\n% Sample valid PDF document content\n%%EOF"
    upload_resp = await client.post(
        "/api/v1/documents",
        data={"knowledge_base_id": kb_id},
        files={"file": ("guide.pdf", pdf_content, "application/pdf")},
    )
    assert upload_resp.status_code == 201
    upload_data = upload_resp.json()
    assert upload_data["filename"] == "guide.pdf"
    assert upload_data["status"] == "UPLOADED"
    assert upload_data["file_size_bytes"] == len(pdf_content)
    assert "document_id" in upload_data
    assert "ingestion_job_id" in upload_data

    doc_id = upload_data["document_id"]
    job_id = upload_data["ingestion_job_id"]

    # Verify storage contains the object
    assert len(storage.objects) == 1

    # 3. Duplicate upload to same KB must be rejected with 409 DUPLICATE_DOCUMENT
    dup_resp = await client.post(
        "/api/v1/documents",
        data={"knowledge_base_id": kb_id},
        files={"file": ("guide_copy.pdf", pdf_content, "application/pdf")},
    )
    assert dup_resp.status_code == 409
    body = dup_resp.json()
    assert body["error"]["code"] == "DUPLICATE_DOCUMENT"

    # 4. Detail endpoint
    detail_resp = await client.get(f"/api/v1/documents/{doc_id}")
    assert detail_resp.status_code == 200
    detail = detail_resp.json()
    assert detail["id"] == doc_id
    assert len(detail["versions"]) == 1
    assert detail["versions"][0]["checksum_sha256"] == upload_data["checksum_sha256"]

    # 5. Download endpoint
    dl_resp = await client.get(f"/api/v1/documents/{doc_id}/download")
    assert dl_resp.status_code == 200
    assert dl_resp.content == pdf_content
    assert dl_resp.headers["content-type"] == "application/pdf"
    assert 'attachment; filename="guide.pdf"' in dl_resp.headers["content-disposition"]

    # 6. Check ingestion job status
    job_resp = await client.get(f"/api/v1/ingestion-jobs/{job_id}")
    assert job_resp.status_code == 200
    job_data = job_resp.json()
    assert job_data["id"] == job_id
    assert job_data["status"] == "PENDING"
    assert job_data["document_id"] == doc_id

    # 7. Reindex endpoint
    reindex_resp = await client.post(f"/api/v1/documents/{doc_id}/reindex")
    assert reindex_resp.status_code == 202
    new_job = reindex_resp.json()
    assert new_job["id"] != job_id
    assert new_job["status"] == "PENDING"

    # 8. Delete document
    del_resp = await client.delete(f"/api/v1/documents/{doc_id}")
    assert del_resp.status_code == 204
    assert len(storage.objects) == 0  # Storage object purged

    # Verify document is gone
    assert (await client.get(f"/api/v1/documents/{doc_id}")).status_code == 404


# -------------------------------------------------------------------------
# Multi-tenant Owner Isolation on Documents and Ingestion Jobs
# -------------------------------------------------------------------------


async def test_document_owner_isolation(test_env) -> None:
    _, client, _, _, owner_b = test_env

    # Owner A creates KB and uploads document
    kb_a = (await client.post("/api/v1/knowledge-bases", json={"name": "Owner A KB"})).json()
    kb_a_id = kb_a["id"]

    pdf_content = b"%PDF-1.4\nOwner A confidential document\n%%EOF"
    upload_a = (
        await client.post(
            "/api/v1/documents",
            data={"knowledge_base_id": kb_a_id},
            files={"file": ("confidential.pdf", pdf_content, "application/pdf")},
        )
    ).json()
    doc_a_id = upload_a["document_id"]
    job_a_id = upload_a["ingestion_job_id"]

    headers_b = {"X-User-Id": str(owner_b)}

    # Owner B cannot list Owner A's documents
    list_b = await client.get("/api/v1/documents", headers=headers_b)
    assert list_b.status_code == 200
    assert len(list_b.json()) == 0

    # Owner B cannot get Owner A's document
    assert (await client.get(f"/api/v1/documents/{doc_a_id}", headers=headers_b)).status_code == 404

    # Owner B cannot download Owner A's document
    assert (
        await client.get(f"/api/v1/documents/{doc_a_id}/download", headers=headers_b)
    ).status_code == 404

    # Owner B cannot reindex Owner A's document
    assert (
        await client.post(f"/api/v1/documents/{doc_a_id}/reindex", headers=headers_b)
    ).status_code == 404

    # Owner B cannot delete Owner A's document
    assert (
        await client.delete(f"/api/v1/documents/{doc_a_id}", headers=headers_b)
    ).status_code == 404

    # Owner B cannot query Owner A's ingestion job
    assert (
        await client.get(f"/api/v1/ingestion-jobs/{job_a_id}", headers=headers_b)
    ).status_code == 404

    # Owner B cannot upload a document targeting Owner A's knowledge base
    unauthorized_upload = await client.post(
        "/api/v1/documents",
        data={"knowledge_base_id": kb_a_id},
        files={"file": ("injected.pdf", pdf_content, "application/pdf")},
        headers=headers_b,
    )
    assert unauthorized_upload.status_code == 404


# -------------------------------------------------------------------------
# Upload Validation and Security Constraints
# -------------------------------------------------------------------------


async def test_upload_rejects_path_traversal_filename(test_env) -> None:
    _, client, _, _, _ = test_env
    kb = (await client.post("/api/v1/knowledge-bases", json={"name": "Security KB"})).json()

    resp = await client.post(
        "/api/v1/documents",
        data={"knowledge_base_id": kb["id"]},
        files={"file": ("../../etc/passwd", b"%PDF-1.4\ncontent\n%%EOF", "application/pdf")},
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "INVALID_FILENAME"


async def test_upload_rejects_unsupported_media_type(test_env) -> None:
    _, client, _, _, _ = test_env
    kb = (await client.post("/api/v1/knowledge-bases", json={"name": "Type Check KB"})).json()

    resp = await client.post(
        "/api/v1/documents",
        data={"knowledge_base_id": kb["id"]},
        files={"file": ("malicious.exe", b"MZ\x90\x00BinaryExe", "application/octet-stream")},
    )
    assert resp.status_code == 415
    assert resp.json()["error"]["code"] == "UNSUPPORTED_MEDIA_TYPE"


async def test_upload_rejects_empty_file(test_env) -> None:
    _, client, _, _, _ = test_env
    kb = (await client.post("/api/v1/knowledge-bases", json={"name": "Empty Check KB"})).json()

    resp = await client.post(
        "/api/v1/documents",
        data={"knowledge_base_id": kb["id"]},
        files={"file": ("empty.txt", b"", "text/plain")},
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "EMPTY_FILE"


async def test_dev_auth_disabled_fails_closed(test_env) -> None:
    app, client, _, _, _ = test_env
    from rag_llm_services_api.core.config import get_settings

    def disabled_auth_settings() -> Settings:
        cfg = get_settings()
        cfg.dev_auth.auth_enabled = False
        return cfg

    app.dependency_overrides[get_settings] = disabled_auth_settings

    kb_resp = await client.get("/api/v1/knowledge-bases")
    assert kb_resp.status_code == 401
    assert kb_resp.json()["error"]["code"] == "UNAUTHORIZED"

    doc_resp = await client.get("/api/v1/documents")
    assert doc_resp.status_code == 401
    assert doc_resp.json()["error"]["code"] == "UNAUTHORIZED"
