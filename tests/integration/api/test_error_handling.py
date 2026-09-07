"""End-to-end integration tests for HTTP error handling on create_app().

Verifies that unhandled exceptions (HTTP 500) and client errors (404, 422)
correctly preserve the correlation request ID in both the X-Request-ID response
header and the {"error": {"request_id": ...}} envelope body.
"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator

import httpx
import pytest
from fastapi import FastAPI
from pydantic import BaseModel

from rag_llm_services_api.core.errors import AppError
from rag_llm_services_api.main import create_app
from rag_llm_services_shared.constants import REQUEST_ID_HEADER

_HEX_UUID_PATTERN = re.compile(r"^[0-9a-f]{32}$")


class _ValidationPayload(BaseModel):
    required_number: int


@pytest.fixture
def app_with_test_routes() -> FastAPI:
    """Instantiate the full application and mount routes that exercise errors."""
    app = create_app()

    @app.get("/test/unhandled")
    async def _unhandled() -> dict[str, str]:
        raise RuntimeError("simulated database or unhandled crash")

    @app.post("/test/validate")
    async def _validate(payload: _ValidationPayload) -> dict[str, int]:
        return {"value": payload.required_number}

    @app.get("/test/app-error")
    async def _app_error() -> dict[str, str]:
        raise AppError("custom business failure", code="CUSTOM_ERROR", status_code=400)

    return app


@pytest.fixture
async def client_server_error(app_with_test_routes: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    """AsyncClient using ASGITransport configured not to re-raise app exceptions."""
    transport = httpx.ASGITransport(app=app_with_test_routes, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


async def test_unhandled_500_generates_request_id_in_header_and_body(
    client_server_error: httpx.AsyncClient,
) -> None:
    """Unhandled exception returns 500, sets X-Request-ID, and matches envelope."""
    response = await client_server_error.get("/test/unhandled")
    assert response.status_code == 500

    header_id = response.headers.get(REQUEST_ID_HEADER)
    assert header_id is not None
    assert _HEX_UUID_PATTERN.fullmatch(header_id) is not None

    body = response.json()
    assert body == {
        "error": {
            "code": "INTERNAL_ERROR",
            "message": "Internal server error",
            "request_id": header_id,
        }
    }


async def test_unhandled_500_preserves_incoming_request_id(
    client_server_error: httpx.AsyncClient,
) -> None:
    """Client-supplied X-Request-ID is echoed on 500 in header and envelope."""
    custom_id = "custom-trace-uuid-12345"
    response = await client_server_error.get(
        "/test/unhandled",
        headers={REQUEST_ID_HEADER: custom_id},
    )
    assert response.status_code == 500
    assert response.headers.get(REQUEST_ID_HEADER) == custom_id

    body = response.json()
    assert body["error"]["request_id"] == custom_id
    assert body["error"]["code"] == "INTERNAL_ERROR"


async def test_unhandled_500_replaces_malformed_request_id(
    client_server_error: httpx.AsyncClient,
) -> None:
    """Malformed client-supplied X-Request-ID is replaced with fresh UUID on 500."""
    response = await client_server_error.get(
        "/test/unhandled",
        headers={REQUEST_ID_HEADER: "bad id! with spaces"},
    )
    assert response.status_code == 500

    header_id = response.headers.get(REQUEST_ID_HEADER)
    assert header_id is not None
    assert header_id != "bad id! with spaces"
    assert _HEX_UUID_PATTERN.fullmatch(header_id) is not None

    body = response.json()
    assert body["error"]["request_id"] == header_id


async def test_app_error_400_includes_request_id_in_header_and_body(
    client_server_error: httpx.AsyncClient,
) -> None:
    """Application error returns declared status and matching request_id."""
    response = await client_server_error.get("/test/app-error")
    assert response.status_code == 400

    header_id = response.headers.get(REQUEST_ID_HEADER)
    assert header_id is not None
    assert _HEX_UUID_PATTERN.fullmatch(header_id) is not None

    body = response.json()
    assert body["error"]["code"] == "CUSTOM_ERROR"
    assert body["error"]["message"] == "custom business failure"
    assert body["error"]["request_id"] == header_id


async def test_validation_error_422_includes_request_id_in_header_and_body(
    client_server_error: httpx.AsyncClient,
) -> None:
    """Validation error returns 422 with matching request_id in header and envelope."""
    response = await client_server_error.post(
        "/test/validate", json={"required_number": "not_an_int"}
    )
    assert response.status_code == 422

    header_id = response.headers.get(REQUEST_ID_HEADER)
    assert header_id is not None
    assert _HEX_UUID_PATTERN.fullmatch(header_id) is not None

    body = response.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert body["error"]["request_id"] == header_id


async def test_not_found_404_includes_request_id_in_header_and_body(
    client_server_error: httpx.AsyncClient,
) -> None:
    """Non-existent path returns 404 with matching request_id in header and envelope."""
    response = await client_server_error.get("/non-existent-route-404")
    assert response.status_code == 404

    header_id = response.headers.get(REQUEST_ID_HEADER)
    assert header_id is not None
    assert _HEX_UUID_PATTERN.fullmatch(header_id) is not None

    body = response.json()
    assert body["error"]["code"] == "NOT_FOUND"
    assert body["error"]["request_id"] == header_id
