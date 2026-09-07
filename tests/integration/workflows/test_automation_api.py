"""Integration tests for n8n automation API contracts."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from uuid import UUID

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import rag_llm_services_api.db.models  # noqa: F401
from rag_llm_services_api.core.config import Settings, get_settings
from rag_llm_services_api.db.base import Base
from rag_llm_services_api.db.session import get_session
from rag_llm_services_api.main import create_app


@pytest.fixture
async def automation_env() -> AsyncIterator[tuple[FastAPI, httpx.AsyncClient, UUID, UUID]]:
    """Build isolated app, in-memory SQLite database, and two tenant identities."""
    owner_a = uuid.UUID("00000000-0000-0000-0000-000000000001")
    owner_b = uuid.UUID("00000000-0000-0000-0000-000000000002")

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(engine, expire_on_commit=False)

    async def override_get_session() -> AsyncIterator[AsyncSession]:
        async with session_maker() as session:
            yield session

    def override_settings() -> Settings:
        cfg = get_settings()
        cfg.dev_auth.auth_enabled = True
        cfg.dev_auth.user_id = owner_a
        return cfg

    app = create_app()
    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_settings] = override_settings

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield app, client, owner_a, owner_b

    await engine.dispose()
    app.dependency_overrides.clear()


async def test_automation_report_sink_persists_owner_scoped_report(automation_env) -> None:
    _, client, owner_a, _ = automation_env

    response = await client.post(
        "/api/v1/automation/reports",
        json={
            "workflow_name": "nightly-rag-evaluation",
            "run_id": "manual-run-001",
            "status": "SUCCEEDED",
            "summary": "Nightly workflow finished",
            "payload": {"evaluation_run_id": "eval-1", "status": "PENDING"},
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["owner_id"] == str(owner_a)
    assert body["workflow_name"] == "nightly-rag-evaluation"
    assert body["run_id"] == "manual-run-001"
    assert body["status"] == "SUCCEEDED"
    assert body["payload_json"] == {"evaluation_run_id": "eval-1", "status": "PENDING"}


async def test_automation_report_retry_is_idempotent(automation_env) -> None:
    _, client, _, _ = automation_env
    payload = {
        "workflow_name": "nightly-rag-evaluation",
        "run_id": "execution-001",
        "status": "SUCCEEDED",
        "summary": "Nightly workflow finished",
        "payload": {"evaluation_run_id": "eval-1"},
    }

    first = await client.post("/api/v1/automation/reports", json=payload)
    second = await client.post("/api/v1/automation/reports", json=payload)

    assert first.status_code == 201
    assert second.status_code == 201
    assert second.json()["id"] == first.json()["id"]


async def test_automation_report_rejects_credential_shaped_payload(automation_env) -> None:
    _, client, _, _ = automation_env

    response = await client.post(
        "/api/v1/automation/reports",
        json={
            "workflow_name": "failure-notification",
            "status": "FAILED",
            "payload": {"accidental": "Bearer " + ("a" * 24)},
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_evaluation_trigger_and_status_are_owner_scoped(automation_env) -> None:
    _, client, owner_a, owner_b = automation_env

    trigger_response = await client.post(
        "/api/v1/evaluations",
        json={
            "trigger_source": "n8n",
            "idempotency_key": "nightly-execution-001",
            "workflow_name": "nightly-rag-evaluation",
            "dataset_name": "baseline-learning-rag",
            "metadata": {"reason": "nightly"},
        },
    )

    assert trigger_response.status_code == 202
    created = trigger_response.json()
    assert created["owner_id"] == str(owner_a)
    assert created["status"] == "PENDING"
    assert created["trigger_source"] == "n8n"
    assert created["idempotency_key"] == "nightly-execution-001"
    assert created["workflow_name"] == "nightly-rag-evaluation"

    run_id = created["id"]
    status_response = await client.get(f"/api/v1/evaluations/{run_id}")
    assert status_response.status_code == 200
    assert status_response.json()["id"] == run_id

    other_owner_response = await client.get(
        f"/api/v1/evaluations/{run_id}",
        headers={"X-User-Id": str(owner_b)},
    )
    assert other_owner_response.status_code == 404


async def test_evaluation_trigger_retry_is_idempotent_per_owner(automation_env) -> None:
    _, client, _, owner_b = automation_env
    payload = {
        "trigger_source": "n8n",
        "idempotency_key": "nightly-execution-002",
        "workflow_name": "nightly-rag-evaluation",
        "dataset_name": "baseline-learning-rag",
        "metadata": {"reason": "nightly"},
    }

    first = await client.post("/api/v1/evaluations", json=payload)
    second = await client.post("/api/v1/evaluations", json=payload)
    other_owner = await client.post(
        "/api/v1/evaluations",
        json=payload,
        headers={"X-User-Id": str(owner_b)},
    )

    assert first.status_code == 202
    assert second.status_code == 202
    assert other_owner.status_code == 202
    assert second.json()["id"] == first.json()["id"]
    assert other_owner.json()["id"] != first.json()["id"]
