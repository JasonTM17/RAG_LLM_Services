"""Run a fixture-safe release acceptance demo through API and worker boundaries."""

from __future__ import annotations

import asyncio
import json
import sys
import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from typing import BinaryIO

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import httpx
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import rag_llm_services_api.db.models  # noqa: F401 - register SQLAlchemy metadata
from rag_llm_services_api.core.config import Settings, get_settings
from rag_llm_services_api.core.errors import NotFoundError
from rag_llm_services_api.db.base import Base
from rag_llm_services_api.db.session import get_session
from rag_llm_services_api.infrastructure.llm import get_llm_provider
from rag_llm_services_api.infrastructure.queue import get_task_queue
from rag_llm_services_api.infrastructure.queue.base import MemoryTaskQueue
from rag_llm_services_api.infrastructure.storage.base import ObjectStoragePort
from rag_llm_services_api.infrastructure.storage.minio import get_object_storage
from rag_llm_services_api.main import create_app
from rag_llm_services_embeddings.fake import FakeEmbeddingProvider
from rag_llm_services_llm.deepseek import FakeLLMProvider
from rag_llm_services_worker.tasks import run_ingestion_task_once

OWNER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
SOURCE_TEXT = (
    "# Hybrid Retrieval\n\n"
    "Hybrid retrieval combines dense vector similarity, keyword search, reranking, "
    "and grounded citations for private study workflows.\n"
)


class InMemoryObjectStorage(ObjectStoragePort):
    """In-memory object storage used only for the offline acceptance demo."""

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
        self,
        object_key: str,
        chunk_size: int = 65536,
    ) -> AsyncIterator[bytes]:
        raw = await self.get_object(object_key)
        for index in range(0, len(raw), chunk_size):
            yield raw[index : index + chunk_size]

    async def delete_object(self, object_key: str) -> None:
        self.objects.pop(object_key, None)

    async def object_exists(self, object_key: str) -> bool:
        return object_key in self.objects

    async def ensure_bucket_exists(self) -> None:
        return None


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def _settings() -> Settings:
    settings = Settings(_env_file=None)
    settings.app.env = "test"
    settings.dev_auth.auth_enabled = True
    settings.dev_auth.user_id = OWNER_ID
    settings.llm.provider = "fake"
    settings.embedding.provider = "fake"
    settings.embedding.reranker_provider = "fake"
    settings.queue.provider = "memory"
    settings.rate_limit.enabled = False
    return settings


async def _build_app() -> tuple[FastAPI, async_sessionmaker[AsyncSession], InMemoryObjectStorage]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    storage = InMemoryObjectStorage()
    queue = MemoryTaskQueue()
    settings = _settings()

    async def override_get_session() -> AsyncIterator[AsyncSession]:
        async with session_maker() as session:
            yield session

    app = create_app()
    app.state.acceptance_engine = engine
    app.state.task_queue = queue
    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_object_storage] = lambda: storage
    app.dependency_overrides[get_task_queue] = lambda: queue
    app.dependency_overrides[get_llm_provider] = lambda: FakeLLMProvider()
    return app, session_maker, storage


async def _run_demo() -> dict[str, object]:
    app, session_maker, storage = await _build_app()
    queue = app.state.task_queue
    headers = {"x-user-id": str(OWNER_ID), "x-request-id": "phase-16-acceptance"}

    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://acceptance") as client:
            live = await client.get("/health/live")
            _require(live.status_code == 200, "liveness endpoint failed")

            kb_response = await client.post(
                "/api/v1/knowledge-bases",
                json={
                    "name": "Phase 16 Acceptance",
                    "description": "Fixture-safe local release acceptance demo",
                },
                headers=headers,
            )
            _require(kb_response.status_code == 201, "knowledge-base creation failed")
            kb_id = kb_response.json()["id"]

            upload_response = await client.post(
                "/api/v1/documents",
                data={"knowledge_base_id": kb_id},
                files={"file": ("phase16.md", SOURCE_TEXT, "text/markdown")},
                headers=headers,
            )
            _require(upload_response.status_code == 201, "document upload failed")
            upload = upload_response.json()
            _require(upload["queued"] is True, "document upload did not enqueue ingestion")
            _require(len(queue.enqueued) == 1, "memory queue did not capture one ingestion task")

            worker_result = await run_ingestion_task_once(
                queue.enqueued[0],
                settings=_settings(),
                session_maker=session_maker,
                object_storage=storage,
                embedding_provider=FakeEmbeddingProvider(dimension=1024),
            )
            _require(worker_result.status == "INDEXED", "worker ingestion did not index document")
            _require(worker_result.chunk_count > 0, "worker ingestion created no chunks")

            job_response = await client.get(
                f"/api/v1/ingestion-jobs/{upload['ingestion_job_id']}",
                headers=headers,
            )
            _require(job_response.status_code == 200, "ingestion job status fetch failed")
            job = job_response.json()
            _require(job["status"] == "INDEXED", "ingestion job did not reach INDEXED")

            document_response = await client.get(
                f"/api/v1/documents/{upload['document_id']}",
                headers=headers,
            )
            _require(document_response.status_code == 200, "document detail fetch failed")
            document = document_response.json()
            _require(document["status"] == "INDEXED", "document did not reach INDEXED")
            _require(document["chunk_count"] > 0, "document detail reports no chunks")

            retrieval_response = await client.post(
                "/api/v1/retrieval/search",
                json={
                    "query": "How does hybrid retrieval support citations?",
                    "method": "hybrid",
                    "filter": {"knowledge_base_id": kb_id},
                    "include_context_bundle": True,
                },
                headers=headers,
            )
            _require(retrieval_response.status_code == 200, "retrieval search failed")
            retrieval = retrieval_response.json()
            _require(retrieval["total_results"] > 0, "retrieval returned no results")
            _require(
                retrieval["context_bundle"]["cited_chunks"][0]["source_id"] == "[S1]",
                "retrieval context did not assign the first citation",
            )

            chat_response = await client.post(
                "/api/v1/chat",
                json={
                    "message": "Explain hybrid retrieval with citations.",
                    "knowledge_base_id": kb_id,
                },
                headers=headers,
            )
            _require(chat_response.status_code == 200, "mocked chat failed")
            chat = chat_response.json()
            _require(chat["provider"] == "fake", "chat used a non-fake provider")
            _require(chat["citations"][0]["source_id"] == "[S1]", "chat did not cite [S1]")

            quiz_response = await client.post(
                "/api/v1/study/quiz",
                json={
                    "topic": "hybrid retrieval",
                    "knowledge_base_id": kb_id,
                    "question_count": 1,
                },
                headers=headers,
            )
            _require(quiz_response.status_code == 200, "study quiz agent failed")
            quiz = quiz_response.json()
            _require(quiz["provider"] == "fake", "study quiz used a non-fake provider")
            _require(quiz["questions"][0]["citations"] == ["[S1]"], "study quiz did not cite [S1]")

            metrics_response = await client.get("/metrics")
            _require(metrics_response.status_code == 200, "metrics endpoint failed")
            _require(
                "rag_http_requests_total" in metrics_response.text,
                "metrics output did not include HTTP request counter",
            )

        return {
            "status": "PASS",
            "owner_id": str(OWNER_ID),
            "knowledge_base_id": kb_id,
            "document_id": upload["document_id"],
            "ingestion_job_id": upload["ingestion_job_id"],
            "worker_status": worker_result.status,
            "chunk_count": worker_result.chunk_count,
            "retrieval_results": retrieval["total_results"],
            "chat_provider": chat["provider"],
            "study_provider": quiz["provider"],
            "citation": chat["citations"][0]["source_id"],
        }
    finally:
        await app.state.acceptance_engine.dispose()
        app.dependency_overrides.clear()


def main() -> int:
    summary = asyncio.run(_run_demo())
    print(json.dumps(summary, indent=2, sort_keys=True))
    print("ACCEPTANCE_DEMO_PASS")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ACCEPTANCE_DEMO_FAIL: {type(exc).__name__}", file=sys.stderr)
        raise SystemExit(1) from exc
