"""Tests for ingestion worker retry policy."""

from __future__ import annotations

import pytest

from rag_llm_services_worker.retry import RetryPolicy


def test_retry_policy_exponential_backoff_caps_delay() -> None:
    policy = RetryPolicy(
        max_retries=3,
        base_delay_seconds=5,
        max_delay_seconds=12,
        jitter=False,
    )

    assert policy.delay_for_retry(1) == 5.0
    assert policy.delay_for_retry(2) == 10.0
    assert policy.delay_for_retry(3) == 12.0
    assert policy.delay_for_retry(4) == 12.0


def test_retry_policy_jitter_is_bounded_and_deterministic_when_factor_supplied() -> None:
    policy = RetryPolicy(
        max_retries=1,
        base_delay_seconds=10,
        max_delay_seconds=100,
        jitter=True,
    )

    assert policy.delay_for_retry(1, jitter_factor=0.0) == 5.0
    assert policy.delay_for_retry(1, jitter_factor=0.5) == 10.0
    assert policy.delay_for_retry(1, jitter_factor=1.0) == 15.0


def test_retry_policy_respects_max_retries_after_completed_attempts() -> None:
    policy = RetryPolicy(
        max_retries=2,
        base_delay_seconds=1,
        max_delay_seconds=10,
        jitter=False,
    )

    assert policy.should_retry(1) is True
    assert policy.should_retry(2) is True
    assert policy.should_retry(3) is False


def test_retry_policy_rejects_zero_or_negative_numbers() -> None:
    policy = RetryPolicy(
        max_retries=1,
        base_delay_seconds=1,
        max_delay_seconds=10,
        jitter=False,
    )

    with pytest.raises(ValueError):
        policy.delay_for_retry(0)
    with pytest.raises(ValueError):
        policy.should_retry(0)
