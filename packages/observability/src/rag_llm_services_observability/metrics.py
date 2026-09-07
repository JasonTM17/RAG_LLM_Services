"""Small in-process metric primitives for service instrumentation.

The project does not expose Prometheus scraping yet, but application services
still need one canonical observability boundary for counters and histograms.
These primitives keep labels allowlisted so application code cannot accidentally
turn user, document, query, or tenant values into high-cardinality metric labels.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from threading import Lock

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


@dataclass(frozen=True)
class HistogramSample:
    """Immutable snapshot of one histogram label set."""

    count: int
    total: float
    buckets: dict[float, int]


class Counter:
    """Thread-safe monotonically increasing counter with allowlisted labels."""

    def __init__(
        self,
        name: str,
        label_names: tuple[str, ...],
        allowed_label_values: Mapping[str, frozenset[str]],
    ) -> None:
        self.name = name
        self._label_names = label_names
        self._allowed_label_values = dict(allowed_label_values)
        self._values: defaultdict[tuple[tuple[str, str], ...], float] = defaultdict(float)
        self._lock = Lock()

    def inc(self, labels: Mapping[str, str], amount: float = 1.0) -> None:
        """Increment a labeled counter by a non-negative amount."""
        if amount < 0:
            raise ValueError("counter amount must be non-negative")
        key = self._label_key(labels)
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
        if set(labels) != set(self._label_names):
            raise ValueError(f"{self.name} requires labels {self._label_names}")
        for label, value in labels.items():
            allowed_values = self._allowed_label_values.get(label)
            if allowed_values is not None and value not in allowed_values:
                raise ValueError(f"{self.name} label {label} value is not allowlisted")
        return tuple((label, str(labels[label])) for label in self._label_names)


class Histogram:
    """Thread-safe histogram with allowlisted labels and cumulative buckets."""

    def __init__(
        self,
        name: str,
        label_names: tuple[str, ...],
        allowed_label_values: Mapping[str, frozenset[str]],
        buckets: tuple[float, ...] = (1, 5, 10, 25, 50, 100, 250, 500, 1000, 2500, 5000),
    ) -> None:
        self.name = name
        self._label_names = label_names
        self._allowed_label_values = dict(allowed_label_values)
        self._buckets = tuple(sorted(buckets))
        self._counts: defaultdict[tuple[tuple[str, str], ...], int] = defaultdict(int)
        self._sums: defaultdict[tuple[tuple[str, str], ...], float] = defaultdict(float)
        self._bucket_counts: defaultdict[tuple[tuple[str, str], ...], dict[float, int]] = (
            defaultdict(lambda: dict.fromkeys(self._buckets, 0))
        )
        self._lock = Lock()

    def observe(self, labels: Mapping[str, str], value: float) -> None:
        """Observe one non-negative value."""
        if value < 0:
            raise ValueError("histogram value must be non-negative")
        key = self._label_key(labels)
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
        if set(labels) != set(self._label_names):
            raise ValueError(f"{self.name} requires labels {self._label_names}")
        for label, value in labels.items():
            allowed_values = self._allowed_label_values.get(label)
            if allowed_values is not None and value not in allowed_values:
                raise ValueError(f"{self.name} label {label} value is not allowlisted")
        return tuple((label, str(labels[label])) for label in self._label_names)


RETRIEVAL_QUERY_TOTAL = Counter(
    name="rag_retrieval_query_total",
    label_names=("method",),
    allowed_label_values={"method": RETRIEVAL_METHODS},
)

RETRIEVAL_STAGE_LATENCY_MS = Histogram(
    name="rag_retrieval_stage_latency_ms",
    label_names=("stage",),
    allowed_label_values={"stage": RETRIEVAL_STAGES},
)


def record_retrieval_query(method: str) -> None:
    """Increment the retrieval query counter using a bounded method label."""
    RETRIEVAL_QUERY_TOTAL.inc({"method": method})


def record_retrieval_stage_latency(stage: str, latency_ms: float) -> None:
    """Observe retrieval latency for one bounded pipeline stage label."""
    RETRIEVAL_STAGE_LATENCY_MS.observe({"stage": stage}, max(0.0, latency_ms))


def reset_retrieval_metrics() -> None:
    """Reset retrieval metrics for deterministic tests."""
    RETRIEVAL_QUERY_TOTAL.reset()
    RETRIEVAL_STAGE_LATENCY_MS.reset()
