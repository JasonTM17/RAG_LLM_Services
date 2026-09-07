"""Retry policy helpers for ingestion worker tasks."""

from __future__ import annotations

import random
from dataclasses import dataclass

from rag_llm_services_api.core.config import Settings


@dataclass(frozen=True)
class RetryPolicy:
    """Bounded exponential retry settings shared by tests and Celery wiring."""

    max_retries: int
    base_delay_seconds: int
    max_delay_seconds: int
    jitter: bool = True

    @classmethod
    def from_settings(cls, settings: Settings) -> RetryPolicy:
        """Build retry policy from application settings."""
        return cls(
            max_retries=settings.queue.ingestion_task_max_retries,
            base_delay_seconds=settings.queue.ingestion_task_retry_backoff_seconds,
            max_delay_seconds=settings.queue.ingestion_task_retry_backoff_max_seconds,
            jitter=settings.queue.ingestion_task_retry_jitter,
        )

    def should_retry(self, completed_attempts: int) -> bool:
        """Return whether another retry is allowed after completed attempts."""
        if completed_attempts < 1:
            raise ValueError("completed_attempts must be at least 1")
        return completed_attempts <= self.max_retries

    def delay_for_retry(self, retry_number: int, *, jitter_factor: float | None = None) -> float:
        """Return exponential retry delay for a one-based retry number."""
        if retry_number < 1:
            raise ValueError("retry_number must be at least 1")
        delay = min(
            float(self.max_delay_seconds),
            float(self.base_delay_seconds) * (2 ** (retry_number - 1)),
        )
        if not self.jitter:
            return delay
        factor = random.random() if jitter_factor is None else jitter_factor
        bounded_factor = min(1.0, max(0.0, factor))
        return round(delay * (0.5 + bounded_factor), 3)
