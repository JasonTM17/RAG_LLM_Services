"""Unit tests for the request ID middleware.

No network and no server: requests run through ``httpx.ASGITransport``
against a minimal FastAPI app so only the middleware under test is exercised.
"""

from __future__ import annotations

import re

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from rag_llm_services_api.core.middleware import RequestIdMiddleware
from rag_llm_services_observability.context import get_request_id
from rag_llm_services_shared.constants import REQUEST_ID_HEADER

_GENERATED_ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")


@pytest.fixture
def app() -> FastAPI:
    """Minimal app: the middleware plus one plain GET route."""
    test_app = FastAPI()
    test_app.add_middleware(RequestIdMiddleware)

    @test_app.get("/ping")
    async def ping() -> dict[str, bool]:
        return {"ok": True}

    return test_app


@pytest.fixture
async def client(app: FastAPI) -> AsyncClient:
    """In-process async client bound to the test app via ASGITransport."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as async_client:
        yield async_client


async def test_valid_incoming_request_id_is_echoed(client: AsyncClient) -> None:
    """A well-formed client-supplied ID passes through unchanged."""
    response = await client.get("/ping", headers={REQUEST_ID_HEADER: "abcd1234-efgh5678"})
    assert response.status_code == 200
    assert response.headers[REQUEST_ID_HEADER] == "abcd1234-efgh5678"


async def test_malformed_request_id_is_replaced_with_generated_uuid(
    client: AsyncClient,
) -> None:
    """A malformed client-supplied ID is replaced, never echoed."""
    response = await client.get("/ping", headers={REQUEST_ID_HEADER: "bad id!!"})
    echoed = response.headers[REQUEST_ID_HEADER]
    assert echoed != "bad id!!"
    assert _GENERATED_ID_PATTERN.fullmatch(echoed) is not None


async def test_absent_request_id_is_generated(client: AsyncClient) -> None:
    """A missing ID is generated and present on the response."""
    response = await client.get("/ping")
    echoed = response.headers[REQUEST_ID_HEADER]
    assert _GENERATED_ID_PATTERN.fullmatch(echoed) is not None


async def test_sequential_requests_get_different_generated_ids(
    client: AsyncClient,
) -> None:
    """Generated IDs differ per request and the ContextVar resets afterwards."""
    first = await client.get("/ping")
    second = await client.get("/ping")
    first_id = first.headers[REQUEST_ID_HEADER]
    second_id = second.headers[REQUEST_ID_HEADER]
    assert first_id != second_id
    assert _GENERATED_ID_PATTERN.fullmatch(first_id) is not None
    assert _GENERATED_ID_PATTERN.fullmatch(second_id) is not None
    assert get_request_id() is None
