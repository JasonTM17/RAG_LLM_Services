"""Tests for low-cardinality in-process observability metrics."""

from __future__ import annotations

import pytest

from rag_llm_services_observability.metrics import (
    RETRIEVAL_QUERY_TOTAL,
    RETRIEVAL_STAGE_LATENCY_MS,
    WORKER_INGESTION_JOB_DURATION_MS,
    WORKER_INGESTION_JOB_TOTAL,
    WORKER_QUEUE_DEPTH,
    record_retrieval_query,
    record_retrieval_stage_latency,
    record_worker_ingestion_duration,
    record_worker_ingestion_job,
    record_worker_queue_depth,
    reset_retrieval_metrics,
    reset_worker_metrics,
)


@pytest.fixture(autouse=True)
def clean_metrics() -> None:
    """Keep global metric snapshots deterministic."""
    reset_retrieval_metrics()
    reset_worker_metrics()


def test_retrieval_metrics_record_counter_and_histogram_samples() -> None:
    record_retrieval_query("hybrid")
    record_retrieval_stage_latency("vector", 12.5)

    counters = RETRIEVAL_QUERY_TOTAL.snapshot()
    histograms = RETRIEVAL_STAGE_LATENCY_MS.snapshot()

    assert counters[(("method", "hybrid"),)] == 1.0
    sample = histograms[(("stage", "vector"),)]
    assert sample.count == 1
    assert sample.total == 12.5
    assert sample.buckets[25] == 1


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
    assert duration.total == 42.0
    assert WORKER_QUEUE_DEPTH.snapshot()[()] == 7.0


def test_worker_metrics_reject_unbounded_status_labels() -> None:
    with pytest.raises(ValueError, match="allowlisted"):
        record_worker_ingestion_job("job:00000000-0000-0000-0000-000000000001")

    with pytest.raises(ValueError, match="allowlisted"):
        record_worker_ingestion_duration("tenant-specific", 1.0)


def test_worker_metrics_allow_retrying_status() -> None:
    record_worker_ingestion_job("retrying")
    record_worker_ingestion_duration("retrying", 5.0)

    assert WORKER_INGESTION_JOB_TOTAL.snapshot()[(("status", "retrying"),)] == 1.0
    assert WORKER_INGESTION_JOB_DURATION_MS.snapshot()[(("status", "retrying"),)].count == 1
