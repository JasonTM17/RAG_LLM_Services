"""Tests for low-cardinality in-process observability metrics."""

from __future__ import annotations

import pytest

from rag_llm_services_observability.metrics import (
    RETRIEVAL_QUERY_TOTAL,
    RETRIEVAL_STAGE_LATENCY_MS,
    record_retrieval_query,
    record_retrieval_stage_latency,
    reset_retrieval_metrics,
)


@pytest.fixture(autouse=True)
def clean_metrics() -> None:
    """Keep global metric snapshots deterministic."""
    reset_retrieval_metrics()


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
