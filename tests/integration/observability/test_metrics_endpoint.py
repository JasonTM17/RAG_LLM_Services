"""Integration tests for the Prometheus metrics endpoint."""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest

from rag_llm_services_api.main import create_app
from rag_llm_services_observability.metrics import reset_all_metrics
from rag_llm_services_shared.constants import REQUEST_ID_HEADER


@pytest.fixture
async def metrics_client() -> AsyncIterator[httpx.AsyncClient]:
    """Build an in-process API client; /metrics must not touch external services."""
    reset_all_metrics()
    app = create_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        yield client
    app.dependency_overrides.clear()
    reset_all_metrics()


async def test_metrics_endpoint_returns_expected_names_without_external_dependencies(
    metrics_client: httpx.AsyncClient,
) -> None:
    live = await metrics_client.get(
        "/health/live",
        headers={REQUEST_ID_HEADER: "metrics-test-req"},
    )
    assert live.status_code == 200

    response = await metrics_client.get("/metrics")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    body = response.text
    for metric_name in (
        "rag_http_requests_total",
        "rag_http_request_duration_seconds",
        "rag_queries_total",
        "rag_retrieval_duration_seconds",
        "rag_ingestion_documents_total",
        "rag_llm_requests_total",
        "rag_errors_total",
        "rag_worker_queue_depth",
    ):
        assert metric_name in body
    assert 'route="/health/live"' in body
    assert 'status_class="2xx"' in body
    assert "metrics-test-req" not in body


async def test_metrics_endpoint_records_client_errors_with_template_route(
    metrics_client: httpx.AsyncClient,
) -> None:
    await metrics_client.get("/api/v1/nope")

    response = await metrics_client.get("/metrics")

    assert response.status_code == 200
    body = response.text
    assert 'route="other"' in body
    assert 'status_class="4xx"' in body
    assert "nope" not in body
