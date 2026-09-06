"""Integration tests for the health endpoints.

Fully offline: the app is exercised through ``httpx.ASGITransport``, so no
server process, no lifespan, no network, and no database are involved. The
readiness probes are replaced via ``app.dependency_overrides`` — the real
Postgres/Redis/MinIO probes are never executed here.
"""

import asyncio
import time
from collections.abc import AsyncIterator

import httpx
import pytest
from fastapi import FastAPI

from rag_llm_services_api.api.health import get_ready_checks
from rag_llm_services_api.main import create_app


class FakeCheck:
    """Configurable stand-in for a ``DependencyCheck`` probe."""

    def __init__(
        self,
        name: str,
        *,
        error: Exception | None = None,
        delay: float = 0.0,
    ) -> None:
        self.name = name
        self._error = error
        self._delay = delay

    async def check(self) -> None:
        """Sleep for the configured delay, then raise the configured error."""
        if self._delay:
            await asyncio.sleep(self._delay)
        if self._error is not None:
            raise self._error


@pytest.fixture
async def api_client() -> AsyncIterator[tuple[FastAPI, httpx.AsyncClient]]:
    """App plus an ASGI-transport client; dependency overrides cleaned after."""
    app = create_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        yield app, client
    app.dependency_overrides.clear()


async def test_liveness_returns_healthy(api_client) -> None:
    """Liveness is process-only: always 200 with the fixed body."""
    _, client = api_client
    response = await client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


async def test_ready_all_ok(api_client) -> None:
    """Every probe succeeding yields 200 healthy with all-ok check entries."""
    app, client = api_client
    app.dependency_overrides[get_ready_checks] = lambda: [
        FakeCheck("postgres"),
        FakeCheck("redis"),
        FakeCheck("minio"),
    ]
    response = await client.get("/health/ready")
    assert response.status_code == 200
    assert response.json() == {
        "status": "healthy",
        "checks": {"postgres": "ok", "redis": "ok", "minio": "ok"},
    }


async def test_ready_one_failing_is_degraded(api_client) -> None:
    """A single failing probe degrades readiness but keeps ok entries."""
    app, client = api_client
    app.dependency_overrides[get_ready_checks] = lambda: [
        FakeCheck("postgres"),
        FakeCheck("redis", error=RuntimeError("connection refused")),
        FakeCheck("minio"),
    ]
    response = await client.get("/health/ready")
    assert response.status_code == 503
    assert response.json() == {
        "status": "degraded",
        "checks": {"postgres": "ok", "redis": "error", "minio": "ok"},
    }


async def test_ready_all_failing_is_unhealthy(api_client) -> None:
    """All probes failing maps to 503 unhealthy with every entry in error."""
    app, client = api_client
    app.dependency_overrides[get_ready_checks] = lambda: [
        FakeCheck("postgres", error=ConnectionError("down")),
        FakeCheck("redis", error=RuntimeError("down")),
    ]
    response = await client.get("/health/ready")
    assert response.status_code == 503
    assert response.json() == {
        "status": "unhealthy",
        "checks": {"postgres": "error", "redis": "error"},
    }


async def test_ready_zero_checks_is_unhealthy(api_client) -> None:
    """No configured dependencies means readiness cannot be proven: 503."""
    app, client = api_client
    # Rule PIE807 would suggest `list` here, but FastAPI introspects the
    # override's signature and builtins like list() break dependency solving.
    app.dependency_overrides[get_ready_checks] = lambda: []  # noqa: PIE807
    response = await client.get("/health/ready")
    assert response.status_code == 503
    assert response.json() == {"status": "unhealthy", "checks": {}}


async def test_ready_timeout_is_bounded(api_client, monkeypatch) -> None:
    """A hanging probe is cut off by the per-check timeout, promptly."""
    app, client = api_client
    monkeypatch.setattr("rag_llm_services_api.api.health.CHECK_TIMEOUT_SECONDS", 0.05)
    app.dependency_overrides[get_ready_checks] = lambda: [FakeCheck("postgres", delay=5.0)]
    start = time.monotonic()
    response = await client.get("/health/ready")
    elapsed = time.monotonic() - start
    assert response.status_code == 503
    assert response.json() == {"status": "unhealthy", "checks": {"postgres": "error"}}
    assert elapsed < 2.0


async def test_api_v1_unknown_route_returns_error_envelope(api_client) -> None:
    """Unknown /api/v1 routes get the 404 error envelope with a request id."""
    _, client = api_client
    response = await client.get("/api/v1/nope")
    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "NOT_FOUND"
    assert body["error"]["request_id"]
