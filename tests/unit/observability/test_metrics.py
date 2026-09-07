"""Tests for low-cardinality in-process observability metrics."""

from __future__ import annotations

import pytest

from rag_llm_services_llm.usage import LLMUsage
from rag_llm_services_observability.metrics import (
    RAG_HTTP_REQUESTS_TOTAL,
    RAG_INGESTION_CHUNKS_TOTAL,
    RAG_LLM_INPUT_TOKENS_TOTAL,
    RAG_LLM_REQUESTS_TOTAL,
    RAG_RETRIEVED_CHUNKS,
    RETRIEVAL_QUERY_TOTAL,
    RETRIEVAL_STAGE_LATENCY_MS,
    WORKER_INGESTION_JOB_DURATION_MS,
    WORKER_INGESTION_JOB_TOTAL,
    WORKER_QUEUE_DEPTH,
    generate_latest,
    record_http_request,
    record_ingestion_chunks,
    record_ingestion_document,
    record_ingestion_duration,
    record_llm_request,
    record_retrieval_query,
    record_retrieval_stage_latency,
    record_retrieved_chunks,
    record_worker_ingestion_duration,
    record_worker_ingestion_job,
    record_worker_queue_depth,
    reset_all_metrics,
    reset_ingestion_metrics,
    reset_llm_metrics,
)


@pytest.fixture(autouse=True)
def clean_metrics() -> None:
    """Keep global metric snapshots deterministic."""
    reset_all_metrics()


def test_retrieval_metrics_record_counter_and_histogram_samples() -> None:
    record_retrieval_query("hybrid")
    record_retrieval_stage_latency("vector", 12.5)

    counters = RETRIEVAL_QUERY_TOTAL.snapshot()
    histograms = RETRIEVAL_STAGE_LATENCY_MS.snapshot()

    assert counters[(("method", "hybrid"),)] == 1.0
    sample = histograms[(("stage", "vector"),)]
    assert sample.count == 1
    assert sample.total == 0.0125
    assert sample.buckets[0.025] == 1
    assert RAG_RETRIEVED_CHUNKS.snapshot() == {}


def test_retrieval_metrics_reject_high_cardinality_labels() -> None:
    with pytest.raises(ValueError, match="allowlisted"):
        record_retrieval_stage_latency("document:00000000-0000-0000-0000-000000000001", 1.0)

    with pytest.raises(ValueError, match="allowlisted"):
        record_retrieval_query("query text with user supplied value")


def test_worker_metrics_record_counter_duration_and_queue_depth() -> None:
    record_worker_ingestion_job("indexed")
    record_worker_ingestion_duration("indexed", 42.0)
    record_worker_queue_depth(7)

    assert WORKER_INGESTION_JOB_TOTAL.snapshot()[(("status", "indexed"),)] == 1.0
    duration = WORKER_INGESTION_JOB_DURATION_MS.snapshot()[(("status", "indexed"),)]
    assert duration.count == 1
    assert duration.total == 0.042
    assert WORKER_QUEUE_DEPTH.snapshot()[()] == 7.0


def test_worker_metrics_normalize_unbounded_status_labels() -> None:
    record_worker_ingestion_job("job:00000000-0000-0000-0000-000000000001")
    record_worker_ingestion_duration("tenant-specific", 1.0)

    assert WORKER_INGESTION_JOB_TOTAL.snapshot()[(("status", "failed"),)] == 1.0
    assert WORKER_INGESTION_JOB_DURATION_MS.snapshot()[(("status", "failed"),)].count == 1


def test_worker_metrics_allow_retrying_status() -> None:
    record_worker_ingestion_job("retrying")
    record_worker_ingestion_duration("retrying", 5.0)

    assert WORKER_INGESTION_JOB_TOTAL.snapshot()[(("status", "retrying"),)] == 1.0
    assert WORKER_INGESTION_JOB_DURATION_MS.snapshot()[(("status", "retrying"),)].count == 1


def test_http_metrics_normalize_route_and_status_class() -> None:
    record_http_request(
        method="GET",
        route="/api/v1/documents/00000000-0000-0000-0000-000000000001",
        status_code=404,
        duration_seconds=0.031,
    )

    samples = RAG_HTTP_REQUESTS_TOTAL.snapshot()
    assert samples[(("method", "GET"), ("route", "other"), ("status_class", "4xx"))] == 1.0


def test_ingestion_metrics_record_outcomes_and_chunk_count() -> None:
    record_ingestion_document("INDEXED")
    record_ingestion_duration("INDEXED", 2500.0)
    record_ingestion_chunks("INDEXED", 3)

    assert RAG_INGESTION_CHUNKS_TOTAL.snapshot()[(("status", "indexed"),)] == 3.0
    reset_ingestion_metrics()
    assert RAG_INGESTION_CHUNKS_TOTAL.snapshot() == {}


def test_llm_metrics_record_usage_without_query_labels() -> None:
    usage = LLMUsage(input_tokens=12, output_tokens=5, total_tokens=17, estimated_cost_usd=0.001)

    record_llm_request(provider="fake", status="succeeded", latency_ms=125.0, usage=usage)

    assert RAG_LLM_REQUESTS_TOTAL.snapshot()[(("provider", "fake"), ("status", "succeeded"))] == 1.0
    assert RAG_LLM_INPUT_TOKENS_TOTAL.snapshot()[(("provider", "fake"),)] == 12.0
    reset_llm_metrics()
    assert RAG_LLM_REQUESTS_TOTAL.snapshot() == {}


def test_retrieved_chunks_histogram_uses_bounded_method_label() -> None:
    record_retrieved_chunks("hybrid", 4)

    sample = RAG_RETRIEVED_CHUNKS.snapshot()[(("method", "hybrid"),)]
    assert sample.count == 1
    assert sample.total == 4.0


def test_generate_latest_renders_prometheus_text_format() -> None:
    record_worker_queue_depth(2)

    output = generate_latest()

    assert "# HELP rag_http_requests_total" in output
    assert "# TYPE rag_worker_queue_depth gauge" in output
    assert "rag_worker_queue_depth 2" in output
