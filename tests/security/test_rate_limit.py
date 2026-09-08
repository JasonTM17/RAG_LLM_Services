"""Security tests for API rate limiting and response hardening."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from rag_llm_services_api.core.middleware import RequestIdMiddleware, SecurityHeadersMiddleware
from rag_llm_services_api.core.rate_limit import (
    InMemoryRateLimitStore,
    RateLimitDecision,
    RateLimitMiddleware,
)
from rag_llm_services_shared.constants import REQUEST_ID_HEADER


class FailingStore:
    async def hit(self, key: str, *, limit: int, window_seconds: int) -> RateLimitDecision:
        del key, limit, window_seconds
        raise RuntimeError("store down")


def _build_app(store: object, *, fail_closed: bool = True) -> FastAPI:
    app = FastAPI()
    app.add_middleware(
        RateLimitMiddleware,
        enabled=True,
        requests_per_window=2,
        window_seconds=60,
        store=store,
        fail_closed=fail_closed,
    )
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RequestIdMiddleware)

    @app.get("/api/v1/chat")
    async def chat_probe() -> dict[str, bool]:
        return {"ok": True}

    @app.get("/health/live")
    async def health_probe() -> dict[str, bool]:
        return {"ok": True}

    return app


def _client(app: FastAPI) -> AsyncClient:
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


@pytest.mark.asyncio
async def test_rate_limit_returns_structured_429_after_window_is_exceeded() -> None:
    app = _build_app(InMemoryRateLimitStore())
    async with _client(app) as client:
        assert (await client.get("/api/v1/chat")).status_code == 200
        second = await client.get("/api/v1/chat")
        limited = await client.get("/api/v1/chat")

    assert second.headers["X-RateLimit-Remaining"] == "0"
    assert limited.status_code == 429
    assert limited.json()["error"]["code"] == "RATE_LIMIT_EXCEEDED"
    assert 1 <= int(limited.headers["Retry-After"]) <= 60
    assert REQUEST_ID_HEADER in limited.headers
    assert limited.headers["X-Content-Type-Options"] == "nosniff"


@pytest.mark.asyncio
async def test_rate_limit_skips_health_endpoints() -> None:
    app = _build_app(InMemoryRateLimitStore())
    async with _client(app) as client:
        responses = [await client.get("/health/live") for _ in range(4)]

    assert [response.status_code for response in responses] == [200, 200, 200, 200]
    assert all("X-RateLimit-Limit" not in response.headers for response in responses)


@pytest.mark.asyncio
async def test_rate_limit_fails_closed_when_store_is_unavailable() -> None:
    app = _build_app(FailingStore(), fail_closed=True)
    async with _client(app) as client:
        response = await client.get("/api/v1/chat")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "RATE_LIMIT_UNAVAILABLE"
