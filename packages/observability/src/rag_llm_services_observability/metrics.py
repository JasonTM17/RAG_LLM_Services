"""Prometheus-compatible in-process metrics for service instrumentation.

The registry intentionally owns every metric label name and value allowlist.
Application code records events through small facade functions, so user IDs,
document IDs, request IDs, filenames, and raw queries cannot become Prometheus
labels by accident.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Lock, Thread
from typing import Any, Literal, Protocol

CONTENT_TYPE_LATEST = "text/plain; version=0.0.4; charset=utf-8"

MetricType = Literal["counter", "gauge", "histogram"]

FORBIDDEN_LABEL_NAMES = frozenset(
    {
        "user_id",
        "owner_id",
        "tenant_id",
        "request_id",
        "document_id",
        "version_id",
        "job_id",
        "filename",
        "file_name",
        "raw_filename",
        "query",
        "raw_query",
        "prompt",
    }
)

HTTP_METHODS = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD", "OTHER"})
HTTP_ROUTES = frozenset(
    {
        "/health/live",
        "/health/ready",
        "/metrics",
        "/api/v1/chat",
        "/api/v1/chat/stream",
        "/api/v1/automation/reports",
        "/api/v1/evaluations",
        "/api/v1/evaluations/{run_id}",
        "/api/v1/knowledge-bases",
        "/api/v1/knowledge-bases/{kb_id}",
        "/api/v1/documents",
        "/api/v1/documents/{document_id}",
        "/api/v1/documents/{document_id}/download",
        "/api/v1/documents/{document_id}/reindex",
        "/api/v1/ingestion-jobs/queue",
        "/api/v1/ingestion-jobs/{job_id}",
        "/api/v1/retrieval/search",
        "/api/v1/study/quiz",
        "/api/v1/study/flashcards",
        "/api/v1/study/learning-plan",
        "other",
    }
)
HTTP_STATUS_CLASSES = frozenset({"1xx", "2xx", "3xx", "4xx", "5xx", "unknown"})

RETRIEVAL_STAGES = frozenset(
    {
        "normalize",
        "vector",
        "keyword",
        "fusion",
        "rerank",
        "context",
        "total",
    }
)
RETRIEVAL_METHODS = frozenset({"vector", "keyword", "hybrid"})
INGESTION_STATUSES = frozenset({"indexed", "failed", "skipped", "retrying"})
LLM_PROVIDERS = frozenset({"fake", "deepseek", "unknown"})
LLM_STATUSES = frozenset({"succeeded", "failed"})
ERROR_COMPONENTS = frozenset(
    {"http", "health", "retrieval", "ingestion", "embedding", "llm", "queue", "worker"}
)
ERROR_KINDS = frozenset(
    {
        "client_error",
        "server_error",
        "exception",
        "validation_error",
        "not_found",
        "upstream_unavailable",
        "configuration_error",
        "unknown",
    }
)
CACHE_NAMES = frozenset({"retrieval"})
WORKER_JOB_STATUSES = INGESTION_STATUSES

HTTP_LATENCY_BUCKETS_SECONDS = (
    0.005,
    0.01,
    0.025,
    0.05,
    0.1,
    0.25,
    0.5,
    1.0,
    2.5,
    5.0,
    10.0,
    30.0,
)
RAG_LATENCY_BUCKETS_SECONDS = (0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0)
LLM_LATENCY_BUCKETS_SECONDS = (0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0)
INGESTION_LATENCY_BUCKETS_SECONDS = (
    0.1,
    0.5,
    1.0,
    2.5,
    5.0,
    10.0,
    30.0,
    60.0,
    120.0,
    300.0,
    600.0,
)
CHUNK_BUCKETS = (0.0, 1.0, 2.0, 5.0, 10.0, 25.0, 50.0, 100.0, 250.0, 500.0)


@dataclass(frozen=True)
class HistogramSample:
    """Immutable snapshot of one histogram label set."""

    count: int
    total: float
    buckets: dict[float, int]


class Metric(Protocol):
    """Small protocol shared by all local metric primitives."""

    name: str
    help_text: str
    metric_type: MetricType
    label_names: tuple[str, ...]

    def reset(self) -> None:
        """Clear samples for deterministic tests."""
        ...


def _label_key(
    *,
    metric_name: str,
    label_names: tuple[str, ...],
    allowed_label_values: Mapping[str, frozenset[str]],
    labels: Mapping[str, str],
) -> tuple[tuple[str, str], ...]:
    if set(labels) != set(label_names):
        raise ValueError(f"{metric_name} requires labels {label_names}")
    forbidden = set(label_names) & FORBIDDEN_LABEL_NAMES
    if forbidden:
        raise ValueError(f"{metric_name} has forbidden label names: {sorted(forbidden)}")
    for label, value in labels.items():
        allowed_values = allowed_label_values.get(label)
        if allowed_values is not None and value not in allowed_values:
            raise ValueError(f"{metric_name} label {label} value is not allowlisted")
    return tuple((label, str(labels[label])) for label in label_names)


class Counter:
    """Thread-safe monotonically increasing counter with allowlisted labels."""

    metric_type: MetricType = "counter"

    def __init__(
        self,
        name: str,
        help_text: str,
        label_names: tuple[str, ...] = (),
        allowed_label_values: Mapping[str, frozenset[str]] | None = None,
    ) -> None:
        self.name = name
        self.help_text = help_text
        self.label_names = label_names
        self._allowed_label_values = dict(allowed_label_values or {})
        self._values: defaultdict[tuple[tuple[str, str], ...], float] = defaultdict(float)
        self._lock = Lock()

    def inc(self, labels: Mapping[str, str] | None = None, amount: float = 1.0) -> None:
        """Increment a labeled counter by a non-negative amount."""
        if amount < 0:
            raise ValueError("counter amount must be non-negative")
        key = self._label_key(labels or {})
        with self._lock:
            self._values[key] += amount

    def snapshot(self) -> dict[tuple[tuple[str, str], ...], float]:
        """Return a point-in-time copy of all counter samples."""
        with self._lock:
            return dict(self._values)

    def reset(self) -> None:
        """Clear samples for deterministic tests."""
        with self._lock:
            self._values.clear()

    def _label_key(self, labels: Mapping[str, str]) -> tuple[tuple[str, str], ...]:
        return _label_key(
            metric_name=self.name,
            label_names=self.label_names,
            allowed_label_values=self._allowed_label_values,
            labels=labels,
        )


class Histogram:
    """Thread-safe histogram with allowlisted labels and cumulative buckets."""

    metric_type: MetricType = "histogram"

    def __init__(
        self,
        name: str,
        help_text: str,
        label_names: tuple[str, ...] = (),
        allowed_label_values: Mapping[str, frozenset[str]] | None = None,
        buckets: tuple[float, ...] = HTTP_LATENCY_BUCKETS_SECONDS,
    ) -> None:
        self.name = name
        self.help_text = help_text
        self.label_names = label_names
        self._allowed_label_values = dict(allowed_label_values or {})
        self._buckets = tuple(sorted(buckets))
        self._counts: defaultdict[tuple[tuple[str, str], ...], int] = defaultdict(int)
        self._sums: defaultdict[tuple[tuple[str, str], ...], float] = defaultdict(float)
        self._bucket_counts: defaultdict[tuple[tuple[str, str], ...], dict[float, int]] = (
            defaultdict(lambda: dict.fromkeys(self._buckets, 0))
        )
        self._lock = Lock()

    @property
    def buckets(self) -> tuple[float, ...]:
        """Return the configured bucket boundaries."""
        return self._buckets

    def observe(self, labels: Mapping[str, str] | None = None, value: float = 0.0) -> None:
        """Observe one non-negative value."""
        if value < 0:
            raise ValueError("histogram value must be non-negative")
        key = self._label_key(labels or {})
        with self._lock:
            self._counts[key] += 1
            self._sums[key] += value
            for bucket in self._buckets:
                if value <= bucket:
                    self._bucket_counts[key][bucket] += 1

    def snapshot(self) -> dict[tuple[tuple[str, str], ...], HistogramSample]:
        """Return a point-in-time copy of all histogram samples."""
        with self._lock:
            return {
                key: HistogramSample(
                    count=self._counts[key],
                    total=self._sums[key],
                    buckets=dict(self._bucket_counts[key]),
                )
                for key in self._counts
            }

    def reset(self) -> None:
        """Clear samples for deterministic tests."""
        with self._lock:
            self._counts.clear()
            self._sums.clear()
            self._bucket_counts.clear()

    def _label_key(self, labels: Mapping[str, str]) -> tuple[tuple[str, str], ...]:
        return _label_key(
            metric_name=self.name,
            label_names=self.label_names,
            allowed_label_values=self._allowed_label_values,
            labels=labels,
        )


class Gauge:
    """Thread-safe gauge with allowlisted labels."""

    metric_type: MetricType = "gauge"

    def __init__(
        self,
        name: str,
        help_text: str,
        label_names: tuple[str, ...] = (),
        allowed_label_values: Mapping[str, frozenset[str]] | None = None,
    ) -> None:
        self.name = name
        self.help_text = help_text
        self.label_names = label_names
        self._allowed_label_values = dict(allowed_label_values or {})
        self._values: dict[tuple[tuple[str, str], ...], float] = {}
        self._lock = Lock()

    def set(self, labels: Mapping[str, str] | None = None, value: float = 0.0) -> None:
        """Set a gauge value."""
        key = self._label_key(labels or {})
        with self._lock:
            self._values[key] = value

    def snapshot(self) -> dict[tuple[tuple[str, str], ...], float]:
        """Return a point-in-time copy of all gauge samples."""
        with self._lock:
            return dict(self._values)

    def reset(self) -> None:
        """Clear samples for deterministic tests."""
        with self._lock:
            self._values.clear()

    def _label_key(self, labels: Mapping[str, str]) -> tuple[tuple[str, str], ...]:
        return _label_key(
            metric_name=self.name,
            label_names=self.label_names,
            allowed_label_values=self._allowed_label_values,
            labels=labels,
        )


RAG_HTTP_REQUESTS_TOTAL = Counter(
    name="rag_http_requests_total",
    help_text="Total HTTP requests handled by the API.",
    label_names=("method", "route", "status_class"),
    allowed_label_values={
        "method": HTTP_METHODS,
        "route": HTTP_ROUTES,
        "status_class": HTTP_STATUS_CLASSES,
    },
)

RAG_HTTP_REQUEST_DURATION_SECONDS = Histogram(
    name="rag_http_request_duration_seconds",
    help_text="HTTP request duration in seconds.",
    label_names=("method", "route", "status_class"),
    allowed_label_values={
        "method": HTTP_METHODS,
        "route": HTTP_ROUTES,
        "status_class": HTTP_STATUS_CLASSES,
    },
    buckets=HTTP_LATENCY_BUCKETS_SECONDS,
)

RAG_QUERIES_TOTAL = Counter(
    name="rag_queries_total",
    help_text="Total retrieval queries by bounded retrieval method.",
    label_names=("method",),
    allowed_label_values={"method": RETRIEVAL_METHODS},
)

RAG_RETRIEVAL_DURATION_SECONDS = Histogram(
    name="rag_retrieval_duration_seconds",
    help_text="Retrieval pipeline stage duration in seconds.",
    label_names=("stage",),
    allowed_label_values={"stage": RETRIEVAL_STAGES},
    buckets=RAG_LATENCY_BUCKETS_SECONDS,
)

RAG_VECTOR_SEARCH_DURATION_SECONDS = Histogram(
    name="rag_vector_search_duration_seconds",
    help_text="Vector search duration in seconds.",
    buckets=RAG_LATENCY_BUCKETS_SECONDS,
)

RAG_KEYWORD_SEARCH_DURATION_SECONDS = Histogram(
    name="rag_keyword_search_duration_seconds",
    help_text="Keyword search duration in seconds.",
    buckets=RAG_LATENCY_BUCKETS_SECONDS,
)

RAG_RERANK_DURATION_SECONDS = Histogram(
    name="rag_rerank_duration_seconds",
    help_text="Reranking duration in seconds.",
    buckets=RAG_LATENCY_BUCKETS_SECONDS,
)

RAG_RETRIEVED_CHUNKS = Histogram(
    name="rag_retrieved_chunks",
    help_text="Number of chunks returned by retrieval.",
    label_names=("method",),
    allowed_label_values={"method": RETRIEVAL_METHODS},
    buckets=CHUNK_BUCKETS,
)

RAG_INGESTION_DOCUMENTS_TOTAL = Counter(
    name="rag_ingestion_documents_total",
    help_text="Total ingestion pipeline document outcomes.",
    label_names=("status",),
    allowed_label_values={"status": INGESTION_STATUSES},
)

RAG_INGESTION_DURATION_SECONDS = Histogram(
    name="rag_ingestion_duration_seconds",
    help_text="End-to-end ingestion pipeline duration in seconds.",
    label_names=("status",),
    allowed_label_values={"status": INGESTION_STATUSES},
    buckets=INGESTION_LATENCY_BUCKETS_SECONDS,
)

RAG_INGESTION_CHUNKS_TOTAL = Counter(
    name="rag_ingestion_chunks_total",
    help_text="Total chunks produced by successful or failed ingestion attempts.",
    label_names=("status",),
    allowed_label_values={"status": INGESTION_STATUSES},
)

RAG_EMBEDDING_DURATION_SECONDS = Histogram(
    name="rag_embedding_duration_seconds",
    help_text="Embedding provider call duration in seconds.",
    buckets=INGESTION_LATENCY_BUCKETS_SECONDS,
)

RAG_LLM_REQUESTS_TOTAL = Counter(
    name="rag_llm_requests_total",
    help_text="Total LLM provider requests.",
    label_names=("provider", "status"),
    allowed_label_values={"provider": LLM_PROVIDERS, "status": LLM_STATUSES},
)

RAG_LLM_REQUEST_DURATION_SECONDS = Histogram(
    name="rag_llm_request_duration_seconds",
    help_text="LLM provider request duration in seconds.",
    label_names=("provider", "status"),
    allowed_label_values={"provider": LLM_PROVIDERS, "status": LLM_STATUSES},
    buckets=LLM_LATENCY_BUCKETS_SECONDS,
)

RAG_LLM_INPUT_TOKENS_TOTAL = Counter(
    name="rag_llm_input_tokens_total",
    help_text="Total LLM input tokens reported by providers.",
    label_names=("provider",),
    allowed_label_values={"provider": LLM_PROVIDERS},
)

RAG_LLM_OUTPUT_TOKENS_TOTAL = Counter(
    name="rag_llm_output_tokens_total",
    help_text="Total LLM output tokens reported by providers.",
    label_names=("provider",),
    allowed_label_values={"provider": LLM_PROVIDERS},
)

RAG_LLM_ESTIMATED_COST_USD_TOTAL = Counter(
    name="rag_llm_estimated_cost_usd_total",
    help_text="Total estimated LLM cost in USD.",
    label_names=("provider",),
    allowed_label_values={"provider": LLM_PROVIDERS},
)

RAG_ERRORS_TOTAL = Counter(
    name="rag_errors_total",
    help_text="Total low-cardinality application errors by component and kind.",
    label_names=("component", "kind"),
    allowed_label_values={"component": ERROR_COMPONENTS, "kind": ERROR_KINDS},
)

RAG_CACHE_HITS_TOTAL = Counter(
    name="rag_cache_hits_total",
    help_text="Total cache hits by bounded cache namespace.",
    label_names=("cache",),
    allowed_label_values={"cache": CACHE_NAMES},
)

RAG_CACHE_MISSES_TOTAL = Counter(
    name="rag_cache_misses_total",
    help_text="Total cache misses by bounded cache namespace.",
    label_names=("cache",),
    allowed_label_values={"cache": CACHE_NAMES},
)

RAG_WORKER_JOBS_TOTAL = Counter(
    name="rag_worker_jobs_total",
    help_text="Total worker job outcomes.",
    label_names=("status",),
    allowed_label_values={"status": WORKER_JOB_STATUSES},
)

RAG_WORKER_JOB_DURATION_SECONDS = Histogram(
    name="rag_worker_job_duration_seconds",
    help_text="Worker job duration in seconds.",
    label_names=("status",),
    allowed_label_values={"status": WORKER_JOB_STATUSES},
    buckets=INGESTION_LATENCY_BUCKETS_SECONDS,
)

RAG_WORKER_QUEUE_DEPTH = Gauge(
    name="rag_worker_queue_depth",
    help_text="Approximate ingestion worker queue depth.",
)

ALL_METRICS: tuple[Metric, ...] = (
    RAG_HTTP_REQUESTS_TOTAL,
    RAG_HTTP_REQUEST_DURATION_SECONDS,
    RAG_QUERIES_TOTAL,
    RAG_RETRIEVAL_DURATION_SECONDS,
    RAG_VECTOR_SEARCH_DURATION_SECONDS,
    RAG_KEYWORD_SEARCH_DURATION_SECONDS,
    RAG_RERANK_DURATION_SECONDS,
    RAG_RETRIEVED_CHUNKS,
    RAG_INGESTION_DOCUMENTS_TOTAL,
    RAG_INGESTION_DURATION_SECONDS,
    RAG_INGESTION_CHUNKS_TOTAL,
    RAG_EMBEDDING_DURATION_SECONDS,
    RAG_LLM_REQUESTS_TOTAL,
    RAG_LLM_REQUEST_DURATION_SECONDS,
    RAG_LLM_INPUT_TOKENS_TOTAL,
    RAG_LLM_OUTPUT_TOKENS_TOTAL,
    RAG_LLM_ESTIMATED_COST_USD_TOTAL,
    RAG_ERRORS_TOTAL,
    RAG_CACHE_HITS_TOTAL,
    RAG_CACHE_MISSES_TOTAL,
    RAG_WORKER_JOBS_TOTAL,
    RAG_WORKER_JOB_DURATION_SECONDS,
    RAG_WORKER_QUEUE_DEPTH,
)

# Backward-compatible names kept for Phase 05/08 tests and callers while the
# public metric names move to the Phase 10 contract.
RETRIEVAL_QUERY_TOTAL = RAG_QUERIES_TOTAL
RETRIEVAL_STAGE_LATENCY_MS = RAG_RETRIEVAL_DURATION_SECONDS
WORKER_INGESTION_JOB_TOTAL = RAG_WORKER_JOBS_TOTAL
WORKER_INGESTION_JOB_DURATION_MS = RAG_WORKER_JOB_DURATION_SECONDS
WORKER_QUEUE_DEPTH = RAG_WORKER_QUEUE_DEPTH


def _seconds_from_ms(value_ms: float) -> float:
    return max(0.0, value_ms) / 1000.0


def normalize_http_method(method: str) -> str:
    """Normalize HTTP method labels into a bounded allowlist."""
    normalized = method.upper()
    return normalized if normalized in HTTP_METHODS else "OTHER"


def normalize_http_route(route: str | None) -> str:
    """Normalize API route template labels into a bounded allowlist."""
    if route in HTTP_ROUTES:
        return str(route)
    return "other"


def status_class(status_code: int | None) -> str:
    """Convert a status code to a low-cardinality status-class label."""
    if status_code is None or status_code < 100:
        return "unknown"
    return f"{min(status_code // 100, 5)}xx"


def normalize_ingestion_status(status: str) -> str:
    """Normalize document/job status values into the metrics allowlist."""
    normalized = status.strip().lower()
    return normalized if normalized in INGESTION_STATUSES else "failed"


def normalize_llm_provider(provider: str | None) -> str:
    """Normalize provider labels into the metrics allowlist."""
    normalized = (provider or "unknown").strip().lower()
    return normalized if normalized in LLM_PROVIDERS else "unknown"


def record_http_request(
    *,
    method: str,
    route: str | None,
    status_code: int | None,
    duration_seconds: float,
) -> None:
    """Record one HTTP request without user-specific labels."""
    labels = {
        "method": normalize_http_method(method),
        "route": normalize_http_route(route),
        "status_class": status_class(status_code),
    }
    RAG_HTTP_REQUESTS_TOTAL.inc(labels)
    RAG_HTTP_REQUEST_DURATION_SECONDS.observe(labels, max(0.0, duration_seconds))


def record_retrieval_query(method: str) -> None:
    """Increment the retrieval query counter using a bounded method label."""
    RAG_QUERIES_TOTAL.inc({"method": method})


def record_retrieval_stage_latency(stage: str, latency_ms: float) -> None:
    """Observe retrieval latency for one bounded pipeline stage label."""
    latency_seconds = _seconds_from_ms(latency_ms)
    RAG_RETRIEVAL_DURATION_SECONDS.observe({"stage": stage}, latency_seconds)
    if stage == "vector":
        RAG_VECTOR_SEARCH_DURATION_SECONDS.observe(value=latency_seconds)
    elif stage == "keyword":
        RAG_KEYWORD_SEARCH_DURATION_SECONDS.observe(value=latency_seconds)
    elif stage == "rerank":
        RAG_RERANK_DURATION_SECONDS.observe(value=latency_seconds)


def record_retrieved_chunks(method: str, count: int) -> None:
    """Observe the number of chunks returned from a bounded retrieval method."""
    RAG_RETRIEVED_CHUNKS.observe({"method": method}, float(max(0, count)))


def reset_retrieval_metrics() -> None:
    """Reset retrieval metrics for deterministic tests."""
    for metric in (
        RAG_QUERIES_TOTAL,
        RAG_RETRIEVAL_DURATION_SECONDS,
        RAG_VECTOR_SEARCH_DURATION_SECONDS,
        RAG_KEYWORD_SEARCH_DURATION_SECONDS,
        RAG_RERANK_DURATION_SECONDS,
        RAG_RETRIEVED_CHUNKS,
    ):
        metric.reset()


def record_ingestion_document(status: str) -> None:
    """Increment ingestion outcome count."""
    RAG_INGESTION_DOCUMENTS_TOTAL.inc({"status": normalize_ingestion_status(status)})


def record_ingestion_duration(status: str, duration_ms: float) -> None:
    """Observe end-to-end ingestion duration."""
    RAG_INGESTION_DURATION_SECONDS.observe(
        {"status": normalize_ingestion_status(status)}, _seconds_from_ms(duration_ms)
    )


def record_ingestion_chunks(status: str, count: int) -> None:
    """Record chunks produced by an ingestion attempt."""
    RAG_INGESTION_CHUNKS_TOTAL.inc(
        {"status": normalize_ingestion_status(status)}, amount=float(max(0, count))
    )


def record_embedding_duration(duration_ms: float) -> None:
    """Observe one embedding provider call duration."""
    RAG_EMBEDDING_DURATION_SECONDS.observe(value=_seconds_from_ms(duration_ms))


def reset_ingestion_metrics() -> None:
    """Reset ingestion metrics for deterministic tests."""
    for metric in (
        RAG_INGESTION_DOCUMENTS_TOTAL,
        RAG_INGESTION_DURATION_SECONDS,
        RAG_INGESTION_CHUNKS_TOTAL,
        RAG_EMBEDDING_DURATION_SECONDS,
    ):
        metric.reset()


def record_llm_request(
    *,
    provider: str | None,
    status: str,
    latency_ms: float,
    usage: Any | None = None,
) -> None:
    """Record one LLM provider request and optional usage counters."""
    normalized_provider = normalize_llm_provider(provider)
    normalized_status = status if status in LLM_STATUSES else "failed"
    request_labels = {"provider": normalized_provider, "status": normalized_status}
    RAG_LLM_REQUESTS_TOTAL.inc(request_labels)
    RAG_LLM_REQUEST_DURATION_SECONDS.observe(request_labels, _seconds_from_ms(latency_ms))
    if usage is None:
        return
    provider_labels = {"provider": normalized_provider}
    RAG_LLM_INPUT_TOKENS_TOTAL.inc(
        provider_labels, amount=float(max(0, int(getattr(usage, "input_tokens", 0) or 0)))
    )
    RAG_LLM_OUTPUT_TOKENS_TOTAL.inc(
        provider_labels, amount=float(max(0, int(getattr(usage, "output_tokens", 0) or 0)))
    )
    RAG_LLM_ESTIMATED_COST_USD_TOTAL.inc(
        provider_labels,
        amount=float(max(0.0, float(getattr(usage, "estimated_cost_usd", 0.0) or 0.0))),
    )


def reset_llm_metrics() -> None:
    """Reset LLM metrics for deterministic tests."""
    for metric in (
        RAG_LLM_REQUESTS_TOTAL,
        RAG_LLM_REQUEST_DURATION_SECONDS,
        RAG_LLM_INPUT_TOKENS_TOTAL,
        RAG_LLM_OUTPUT_TOKENS_TOTAL,
        RAG_LLM_ESTIMATED_COST_USD_TOTAL,
    ):
        metric.reset()


def record_error(component: str, kind: str = "unknown") -> None:
    """Record one low-cardinality application error."""
    safe_component = component if component in ERROR_COMPONENTS else "http"
    safe_kind = kind if kind in ERROR_KINDS else "unknown"
    RAG_ERRORS_TOTAL.inc({"component": safe_component, "kind": safe_kind})


def record_cache_hit(cache: str) -> None:
    """Record one cache hit for a bounded cache namespace."""
    RAG_CACHE_HITS_TOTAL.inc({"cache": cache})


def record_cache_miss(cache: str) -> None:
    """Record one cache miss for a bounded cache namespace."""
    RAG_CACHE_MISSES_TOTAL.inc({"cache": cache})


def record_worker_ingestion_job(status: str) -> None:
    """Increment a worker ingestion job counter for a bounded status label."""
    RAG_WORKER_JOBS_TOTAL.inc({"status": normalize_ingestion_status(status)})


def record_worker_ingestion_duration(status: str, duration_ms: float) -> None:
    """Observe worker ingestion duration with a bounded status label."""
    RAG_WORKER_JOB_DURATION_SECONDS.observe(
        {"status": normalize_ingestion_status(status)}, _seconds_from_ms(duration_ms)
    )


def record_worker_queue_depth(depth: int) -> None:
    """Set the current approximate ingestion queue depth."""
    RAG_WORKER_QUEUE_DEPTH.set(value=float(max(0, depth)))


def reset_worker_metrics() -> None:
    """Reset worker metrics for deterministic tests."""
    for metric in (RAG_WORKER_JOBS_TOTAL, RAG_WORKER_JOB_DURATION_SECONDS, RAG_WORKER_QUEUE_DEPTH):
        metric.reset()


def reset_all_metrics() -> None:
    """Reset every metric for deterministic tests."""
    for metric in ALL_METRICS:
        metric.reset()


def metric_label_names() -> dict[str, tuple[str, ...]]:
    """Return the label-name contract for every metric."""
    return {metric.name: metric.label_names for metric in ALL_METRICS}


def validate_metric_label_policy() -> list[str]:
    """Return policy errors for forbidden or duplicate metric labels."""
    errors: list[str] = []
    seen_names: set[str] = set()
    for metric in ALL_METRICS:
        if metric.name in seen_names:
            errors.append(f"duplicate metric name: {metric.name}")
        seen_names.add(metric.name)
        forbidden = set(metric.label_names) & FORBIDDEN_LABEL_NAMES
        if forbidden:
            errors.append(f"{metric.name}: forbidden labels {sorted(forbidden)}")
    return errors


def generate_latest() -> str:
    """Render the registry using Prometheus text exposition format 0.0.4."""
    lines: list[str] = []
    for metric in ALL_METRICS:
        lines.append(f"# HELP {metric.name} {_escape_help(metric.help_text)}")
        lines.append(f"# TYPE {metric.name} {metric.metric_type}")
        if isinstance(metric, (Counter, Gauge)):
            for labels, value in sorted(metric.snapshot().items()):
                lines.append(f"{metric.name}{_format_labels(labels)} {_format_value(value)}")
        elif isinstance(metric, Histogram):
            for labels, sample in sorted(metric.snapshot().items()):
                for bucket, count in sample.buckets.items():
                    lines.append(
                        f"{metric.name}_bucket"
                        f"{_format_labels(labels, extra=(('le', _format_value(bucket)),))} "
                        f"{count}"
                    )
                lines.append(
                    f"{metric.name}_bucket"
                    f"{_format_labels(labels, extra=(('le', '+Inf'),))} {sample.count}"
                )
                lines.append(f"{metric.name}_count{_format_labels(labels)} {sample.count}")
                lines.append(
                    f"{metric.name}_sum{_format_labels(labels)} {_format_value(sample.total)}"
                )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _escape_help(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\n", "\\n")


def _escape_label_value(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


def _format_labels(
    labels: tuple[tuple[str, str], ...],
    *,
    extra: tuple[tuple[str, str], ...] = (),
) -> str:
    pairs = (*labels, *extra)
    if not pairs:
        return ""
    return "{" + ",".join(f'{key}="{_escape_label_value(value)}"' for key, value in pairs) + "}"


def _format_value(value: float) -> str:
    return format(value, ".15g")


class _MetricsHandler(BaseHTTPRequestHandler):
    """Serve the shared registry over a tiny stdlib HTTP endpoint."""

    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0]
        if path != "/metrics":
            self.send_error(404, "Not Found")
            return
        body = generate_latest().encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", CONTENT_TYPE_LATEST)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        """Suppress default access logs; structured logging owns observability."""
        del format, args


_SERVER_LOCK = Lock()
_METRICS_SERVER: ThreadingHTTPServer | None = None
_METRICS_THREAD: Thread | None = None


def start_metrics_http_server(host: str = "0.0.0.0", port: int = 9108) -> ThreadingHTTPServer:
    """Start an idempotent background HTTP server exposing ``GET /metrics``."""
    global _METRICS_SERVER, _METRICS_THREAD
    with _SERVER_LOCK:
        if _METRICS_SERVER is not None:
            return _METRICS_SERVER
        server = ThreadingHTTPServer((host, port), _MetricsHandler)
        thread = Thread(
            target=server.serve_forever,
            name="rag-llm-services-metrics",
            daemon=True,
        )
        thread.start()
        _METRICS_SERVER = server
        _METRICS_THREAD = thread
        return server


__all__ = [
    "ALL_METRICS",
    "CONTENT_TYPE_LATEST",
    "FORBIDDEN_LABEL_NAMES",
    "RAG_CACHE_HITS_TOTAL",
    "RAG_CACHE_MISSES_TOTAL",
    "RAG_EMBEDDING_DURATION_SECONDS",
    "RAG_ERRORS_TOTAL",
    "RAG_HTTP_REQUESTS_TOTAL",
    "RAG_HTTP_REQUEST_DURATION_SECONDS",
    "RAG_INGESTION_CHUNKS_TOTAL",
    "RAG_INGESTION_DOCUMENTS_TOTAL",
    "RAG_INGESTION_DURATION_SECONDS",
    "RAG_KEYWORD_SEARCH_DURATION_SECONDS",
    "RAG_LLM_ESTIMATED_COST_USD_TOTAL",
    "RAG_LLM_INPUT_TOKENS_TOTAL",
    "RAG_LLM_OUTPUT_TOKENS_TOTAL",
    "RAG_LLM_REQUESTS_TOTAL",
    "RAG_LLM_REQUEST_DURATION_SECONDS",
    "RAG_QUERIES_TOTAL",
    "RAG_RERANK_DURATION_SECONDS",
    "RAG_RETRIEVAL_DURATION_SECONDS",
    "RAG_RETRIEVED_CHUNKS",
    "RAG_VECTOR_SEARCH_DURATION_SECONDS",
    "RAG_WORKER_JOBS_TOTAL",
    "RAG_WORKER_JOB_DURATION_SECONDS",
    "RAG_WORKER_QUEUE_DEPTH",
    "RETRIEVAL_QUERY_TOTAL",
    "RETRIEVAL_STAGE_LATENCY_MS",
    "WORKER_INGESTION_JOB_DURATION_MS",
    "WORKER_INGESTION_JOB_TOTAL",
    "WORKER_QUEUE_DEPTH",
    "Counter",
    "Gauge",
    "Histogram",
    "HistogramSample",
    "generate_latest",
    "metric_label_names",
    "normalize_http_route",
    "record_cache_hit",
    "record_cache_miss",
    "record_embedding_duration",
    "record_error",
    "record_http_request",
    "record_ingestion_chunks",
    "record_ingestion_document",
    "record_ingestion_duration",
    "record_llm_request",
    "record_retrieval_query",
    "record_retrieval_stage_latency",
    "record_retrieved_chunks",
    "record_worker_ingestion_duration",
    "record_worker_ingestion_job",
    "record_worker_queue_depth",
    "reset_all_metrics",
    "reset_ingestion_metrics",
    "reset_llm_metrics",
    "reset_retrieval_metrics",
    "reset_worker_metrics",
    "start_metrics_http_server",
    "validate_metric_label_policy",
]
