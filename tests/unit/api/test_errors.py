"""Unit tests for the error envelope exception handlers.

No network, no DB: each failure mode is triggered through an in-process
FastAPI app wired with ``register_exception_handlers`` and driven by
``httpx.ASGITransport``. The ``/unhandled`` route uses a transport configured
with ``raise_app_exceptions=False`` because Starlette's ServerErrorMiddleware
re-raises after generating the 500 response (its documented use case).
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

from rag_llm_services_api.core.error_handlers import register_exception_handlers
from rag_llm_services_api.core.errors import AppError
from rag_llm_services_observability.context import request_id_var, set_request_id


@pytest.fixture(autouse=True)
async def _isolate_request_id_context():
    """Reset the request ID ContextVar around each test so no value bleeds."""
    token = request_id_var.set(None)
    yield
    request_id_var.reset(token)


@pytest.fixture
def app() -> FastAPI:
    """App with one route per handled failure mode, plus a control route."""

    class Payload(BaseModel):
        count: int

    test_app = FastAPI()
    register_exception_handlers(test_app)

    @test_app.get("/app-error")
    async def app_error() -> dict[str, str]:
        raise AppError("boom", code="TEST_CODE", status_code=418)

    @test_app.post("/validation")
    async def validation(payload: Payload) -> dict[str, int]:
        return {"count": payload.count}

    @test_app.get("/http-404")
    async def http_404() -> dict[str, str]:
        raise StarletteHTTPException(status_code=404, detail="nope")

    @test_app.get("/unhandled")
    async def unhandled() -> dict[str, str]:
        raise RuntimeError("secret-detail")

    @test_app.get("/ok")
    async def ok() -> dict[str, str]:
        return {}

    return test_app


@pytest.fixture
async def client(app: FastAPI) -> AsyncClient:
    """Client that surfaces unexpected app exceptions as test failures."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as async_client:
        yield async_client


@pytest.fixture
async def client_server_error(app: FastAPI) -> AsyncClient:
    """Client that returns the 500 response instead of re-raising it."""
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as async_client:
        yield async_client


async def test_app_error_maps_to_declared_status_and_code(client: AsyncClient) -> None:
    response = await client.get("/app-error")
    assert response.status_code == 418
    body = response.json()
    assert set(body) == {"error"}
    assert set(body["error"]) == {"code", "message", "request_id"}
    assert body["error"]["code"] == "TEST_CODE"
    assert body["error"]["message"] == "boom"
    assert body["error"]["request_id"] is None


async def test_request_id_is_attached_to_envelope(client: AsyncClient) -> None:
    """The ContextVar value set during the request reaches the envelope."""
    token = set_request_id("fixed-id-12345678")
    try:
        response = await client.get("/app-error")
    finally:
        request_id_var.reset(token)
    assert response.status_code == 418
    assert response.json()["error"]["request_id"] == "fixed-id-12345678"


async def test_validation_error_hides_pydantic_details(client: AsyncClient) -> None:
    response = await client.post("/validation", json={"count": "not-an-int"})
    assert response.status_code == 422
    body = response.json()
    assert set(body) == {"error"}
    assert set(body["error"]) == {"code", "message", "request_id"}
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert body["error"]["message"] == "Request validation failed"
    raw = response.text
    for fragment in (
        "int_parsing",
        "Input should be a valid integer",
        "loc",
        "input",
        "count",
    ):
        assert fragment not in raw


async def test_http_exception_404_maps_to_not_found(client: AsyncClient) -> None:
    response = await client.get("/http-404")
    assert response.status_code == 404
    body = response.json()
    assert set(body) == {"error"}
    assert body["error"]["code"] == "NOT_FOUND"
    assert body["error"]["message"] == "nope"


async def test_unhandled_exception_returns_generic_internal_error(
    client_server_error: AsyncClient,
) -> None:
    response = await client_server_error.get("/unhandled")
    assert response.status_code == 500
    body = response.json()
    assert set(body) == {"error"}
    assert set(body["error"]) == {"code", "message", "request_id"}
    assert body["error"]["code"] == "INTERNAL_ERROR"
    assert body["error"]["message"] == "Internal server error"
    raw = response.text
    for fragment in ("secret-detail", "Traceback", "RuntimeError"):
        assert fragment not in raw


async def test_ok_route_is_not_reshaped(client: AsyncClient) -> None:
    """Successful responses are untouched by the handlers."""
    response = await client.get("/ok")
    assert response.status_code == 200
    assert response.json() == {}
