"""Static metric contract tests for Phase 10 observability."""

from __future__ import annotations

from pathlib import Path

from rag_llm_services_observability.metrics import (
    ALL_METRICS,
    FORBIDDEN_LABEL_NAMES,
    metric_label_names,
    validate_metric_label_policy,
)

REPO_ROOT = Path(__file__).resolve().parents[3]

REQUIRED_METRIC_NAMES = {
    "rag_http_requests_total",
    "rag_http_request_duration_seconds",
    "rag_queries_total",
    "rag_retrieval_duration_seconds",
    "rag_vector_search_duration_seconds",
    "rag_keyword_search_duration_seconds",
    "rag_rerank_duration_seconds",
    "rag_retrieved_chunks",
    "rag_ingestion_documents_total",
    "rag_ingestion_duration_seconds",
    "rag_ingestion_chunks_total",
    "rag_embedding_duration_seconds",
    "rag_llm_requests_total",
    "rag_llm_request_duration_seconds",
    "rag_llm_input_tokens_total",
    "rag_llm_output_tokens_total",
    "rag_llm_estimated_cost_usd_total",
    "rag_errors_total",
    "rag_cache_hits_total",
    "rag_cache_misses_total",
    "rag_worker_jobs_total",
    "rag_worker_job_duration_seconds",
    "rag_worker_queue_depth",
}


def test_required_phase_10_metric_names_are_registered() -> None:
    registered = {metric.name for metric in ALL_METRICS}

    assert REQUIRED_METRIC_NAMES <= registered


def test_metric_label_policy_rejects_high_cardinality_dimensions() -> None:
    assert validate_metric_label_policy() == []

    for metric_name, label_names in metric_label_names().items():
        forbidden = set(label_names) & FORBIDDEN_LABEL_NAMES
        assert not forbidden, f"{metric_name} uses forbidden labels: {sorted(forbidden)}"


def test_metric_names_keep_rag_prefix() -> None:
    for metric in ALL_METRICS:
        assert metric.name.startswith("rag_")


def test_compose_worker_uses_shared_process_pool_for_scraped_metrics() -> None:
    compose = (REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    dockerfile = (REPO_ROOT / "apps" / "worker" / "Dockerfile").read_text(encoding="utf-8")

    assert "WORKER_POOL: ${WORKER_POOL:-threads}" in compose
    assert "WORKER_METRICS_PORT: 9108" in compose
    assert '"${WORKER_METRICS_HOST_PORT:-9108}:9108"' in compose
    assert "--pool=${WORKER_POOL:-threads}" in dockerfile
    assert "--concurrency=${WORKER_CONCURRENCY:-4}" in dockerfile
