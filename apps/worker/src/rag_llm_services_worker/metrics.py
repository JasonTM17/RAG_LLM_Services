"""Worker metric recording facade."""

from __future__ import annotations

from rag_llm_services_observability.metrics import (
    record_error,
    record_worker_ingestion_duration,
    record_worker_ingestion_job,
    record_worker_queue_depth,
)

__all__ = [
    "record_error",
    "record_worker_ingestion_duration",
    "record_worker_ingestion_job",
    "record_worker_queue_depth",
]
