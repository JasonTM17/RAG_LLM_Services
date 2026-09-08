"""Integration tests for the Phase 12 RAG evaluation API."""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import rag_llm_services_api.db.models  # noqa: F401
from rag_llm_services_api.application.evaluation_service import EvaluationApplicationService
from rag_llm_services_api.core.config import Settings, get_settings
from rag_llm_services_api.db.base import Base
from rag_llm_services_api.db.session import get_session
from rag_llm_services_api.infrastructure.queue import get_task_queue
from rag_llm_services_api.infrastructure.queue.base import MemoryTaskQueue
from rag_llm_services_api.infrastructure.repositories.automation import AutomationRepository
from rag_llm_services_api.main import create_app
from rag_llm_services_worker.tasks import run_evaluation_task_once


@dataclass(frozen=True)
class EvaluationTestEnv:
    """Shared integration-test harness for evaluation API and worker."""

    app: FastAPI
    client: httpx.AsyncClient
    owner_id: UUID
    reports_dir: Path
    queue: MemoryTaskQueue
    session_maker: async_sessionmaker[AsyncSession]
    build_settings: Callable[[], Settings]


@pytest.fixture
async def evaluation_env(tmp_path: Path) -> AsyncIterator[EvaluationTestEnv]:
    """Build isolated app, in-memory SQLite database, queue, and report directory."""
    owner_id = uuid.UUID("00000000-0000-0000-0000-000000000001")
    reports_dir = tmp_path / "reports"
    queue = MemoryTaskQueue()

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(engine, expire_on_commit=False)

    async def override_get_session() -> AsyncIterator[AsyncSession]:
        async with session_maker() as session:
            yield session

    def build_settings() -> Settings:
        cfg = Settings(_env_file=None)
        cfg.dev_auth.auth_enabled = True
        cfg.dev_auth.user_id = owner_id
        cfg.evaluation.reports_dir = str(reports_dir)
        return cfg

    app = create_app()
    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_settings] = build_settings
    app.dependency_overrides[get_task_queue] = lambda: queue

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield EvaluationTestEnv(
            app=app,
            client=client,
            owner_id=owner_id,
            reports_dir=reports_dir,
            queue=queue,
            session_maker=session_maker,
            build_settings=build_settings,
        )

    await engine.dispose()
    app.dependency_overrides.clear()


async def test_evaluation_api_enqueues_then_worker_persists_safe_result(
    evaluation_env: EvaluationTestEnv,
) -> None:
    response = await evaluation_env.client.post(
        "/api/v1/evaluations",
        json={
            "trigger_source": "n8n",
            "idempotency_key": "phase-12-nightly-001",
            "workflow_name": "nightly-rag-evaluation",
            "dataset_name": "baseline-learning-rag",
            "metadata": {"reason": "nightly"},
        },
    )

    assert response.status_code == 202
    created = response.json()
    assert created["owner_id"] == str(evaluation_env.owner_id)
    assert created["status"] == "PENDING"
    assert created["result"] is None
    assert len(evaluation_env.queue.evaluation_enqueued) == 1
    assert str(evaluation_env.queue.evaluation_enqueued[0].run_id) == created["id"]

    worker_result = await run_evaluation_task_once(
        evaluation_env.queue.evaluation_enqueued[0],
        settings=evaluation_env.build_settings(),
        session_maker=evaluation_env.session_maker,
    )

    assert worker_result.status == "SUCCEEDED"
    status_response = await evaluation_env.client.get(f"/api/v1/evaluations/{created['id']}")
    assert status_response.status_code == 200
    body = status_response.json()
    assert body["dataset_name"] == "baseline-learning-rag"
    assert body["error_message"] is None
    assert body["result"]["status"] == "PASS"
    assert body["result"]["metrics"]["retrieval_hit_rate"] == 1.0
    assert body["result"]["metrics"]["citation_correctness"] == 1.0
    assert body["report_path"] == body["result"]["report_json_path"]
    assert not Path(body["report_path"]).is_absolute()

    report_files = sorted(evaluation_env.reports_dir.glob("*.json"))
    assert len(report_files) == 1
    assert body["report_path"] == report_files[0].name
    report_payload = json.loads(report_files[0].read_text(encoding="utf-8"))
    for example_summary in report_payload["examples"]:
        assert "question" not in example_summary
        assert "expected_answer" not in example_summary
        assert "answer" not in example_summary


async def test_evaluation_running_status_is_observable_before_completion(
    evaluation_env: EvaluationTestEnv,
) -> None:
    response = await evaluation_env.client.post(
        "/api/v1/evaluations",
        json={
            "idempotency_key": "phase-12-observable-running",
            "dataset_name": "baseline-learning-rag",
        },
    )
    assert response.status_code == 202
    run_id = UUID(response.json()["id"])

    async with evaluation_env.session_maker() as session:
        service = EvaluationApplicationService(
            AutomationRepository(session),
            evaluation_env.build_settings(),
        )
        claim = await service.mark_running(owner_id=evaluation_env.owner_id, run_id=run_id)
        await session.commit()
        assert claim.executed is True

    running_response = await evaluation_env.client.get(f"/api/v1/evaluations/{run_id}")
    assert running_response.status_code == 200
    assert running_response.json()["status"] == "RUNNING"

    async with evaluation_env.session_maker() as session:
        service = EvaluationApplicationService(
            AutomationRepository(session),
            evaluation_env.build_settings(),
        )
        completion = await service.complete_running(owner_id=evaluation_env.owner_id, run_id=run_id)
        await session.commit()
        assert completion.executed is True


async def test_evaluation_api_retry_returns_existing_pending_run(
    evaluation_env: EvaluationTestEnv,
) -> None:
    payload = {
        "trigger_source": "n8n",
        "idempotency_key": "phase-12-nightly-002",
        "workflow_name": "nightly-rag-evaluation",
        "dataset_name": "baseline-learning-rag",
    }

    first = await evaluation_env.client.post("/api/v1/evaluations", json=payload)
    second = await evaluation_env.client.post("/api/v1/evaluations", json=payload)

    assert first.status_code == 202
    assert second.status_code == 202
    assert second.json()["id"] == first.json()["id"]
    assert second.json()["status"] == "PENDING"
    assert len(evaluation_env.queue.evaluation_enqueued) == 2
    assert {payload.run_id for payload in evaluation_env.queue.evaluation_enqueued} == {
        UUID(first.json()["id"])
    }


async def test_duplicate_worker_tasks_execute_only_once(evaluation_env: EvaluationTestEnv) -> None:
    response = await evaluation_env.client.post(
        "/api/v1/evaluations",
        json={
            "idempotency_key": "phase-12-duplicate-worker",
            "dataset_name": "baseline-learning-rag",
        },
    )
    assert response.status_code == 202
    payload = evaluation_env.queue.evaluation_enqueued[0]

    first = await run_evaluation_task_once(
        payload,
        settings=evaluation_env.build_settings(),
        session_maker=evaluation_env.session_maker,
    )
    second = await run_evaluation_task_once(
        payload,
        settings=evaluation_env.build_settings(),
        session_maker=evaluation_env.session_maker,
    )

    assert first.status == "SUCCEEDED"
    assert first.executed is True
    assert second.status == "SUCCEEDED"
    assert second.executed is False


async def test_running_evaluation_retry_does_not_requeue_before_lease_expires(
    evaluation_env: EvaluationTestEnv,
) -> None:
    payload = {
        "idempotency_key": "phase-12-active-running",
        "dataset_name": "baseline-learning-rag",
    }
    response = await evaluation_env.client.post("/api/v1/evaluations", json=payload)
    assert response.status_code == 202
    run_id = UUID(response.json()["id"])

    async with evaluation_env.session_maker() as session:
        service = EvaluationApplicationService(
            AutomationRepository(session),
            evaluation_env.build_settings(),
        )
        claim = await service.mark_running(owner_id=evaluation_env.owner_id, run_id=run_id)
        await session.commit()
        assert claim.executed is True

    retry = await evaluation_env.client.post("/api/v1/evaluations", json=payload)
    assert retry.status_code == 202
    assert retry.json()["id"] == str(run_id)
    assert retry.json()["status"] == "RUNNING"
    assert len(evaluation_env.queue.evaluation_enqueued) == 1

    worker_result = await run_evaluation_task_once(
        evaluation_env.queue.evaluation_enqueued[0],
        settings=evaluation_env.build_settings(),
        session_maker=evaluation_env.session_maker,
    )

    assert worker_result.status == "RUNNING"
    assert worker_result.executed is False


async def test_stale_running_evaluation_retry_requeues_and_worker_reclaims(
    evaluation_env: EvaluationTestEnv,
) -> None:
    payload = {
        "idempotency_key": "phase-12-stale-running",
        "dataset_name": "baseline-learning-rag",
    }
    response = await evaluation_env.client.post("/api/v1/evaluations", json=payload)
    assert response.status_code == 202
    run_id = UUID(response.json()["id"])

    async with evaluation_env.session_maker() as session:
        service = EvaluationApplicationService(
            AutomationRepository(session),
            evaluation_env.build_settings(),
        )
        claim = await service.mark_running(owner_id=evaluation_env.owner_id, run_id=run_id)
        assert claim.executed is True
        claim.run.updated_at = datetime.now(UTC) - timedelta(hours=2)
        await session.commit()

    retry = await evaluation_env.client.post("/api/v1/evaluations", json=payload)
    assert retry.status_code == 202
    assert retry.json()["id"] == str(run_id)
    assert retry.json()["status"] == "RUNNING"
    assert len(evaluation_env.queue.evaluation_enqueued) == 2

    worker_result = await run_evaluation_task_once(
        evaluation_env.queue.evaluation_enqueued[-1],
        settings=evaluation_env.build_settings(),
        session_maker=evaluation_env.session_maker,
    )

    assert worker_result.status == "SUCCEEDED"
    assert worker_result.executed is True


async def test_evaluation_api_records_failed_threshold_run(
    evaluation_env: EvaluationTestEnv,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("EVAL_FAITHFULNESS_THRESHOLD", "0.99")

    response = await evaluation_env.client.post(
        "/api/v1/evaluations",
        json={
            "trigger_source": "api",
            "idempotency_key": "phase-12-threshold-fail",
            "dataset_name": "baseline-learning-rag",
        },
    )
    assert response.status_code == 202

    worker_result = await run_evaluation_task_once(
        evaluation_env.queue.evaluation_enqueued[0],
        settings=evaluation_env.build_settings(),
        session_maker=evaluation_env.session_maker,
    )

    assert worker_result.status == "FAILED"
    status_response = await evaluation_env.client.get(
        f"/api/v1/evaluations/{response.json()['id']}"
    )
    body = status_response.json()
    assert body["status"] == "FAILED"
    assert body["error_message"] == "Evaluation thresholds failed"
    assert body["result"]["status"] == "FAIL"
    assert any("faithfulness" in failure for failure in body["result"]["failures"])


async def test_evaluation_api_rejects_unsafe_dataset_name(
    evaluation_env: EvaluationTestEnv,
) -> None:
    response = await evaluation_env.client.post(
        "/api/v1/evaluations",
        json={"dataset_name": "../private"},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
