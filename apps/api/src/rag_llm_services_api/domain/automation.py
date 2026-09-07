"""Domain statuses for automation and evaluation orchestration."""

from __future__ import annotations

from enum import StrEnum


class AutomationRunStatus(StrEnum):
    """Bounded statuses emitted by n8n workflow reports."""

    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class EvaluationRunStatus(StrEnum):
    """Minimal evaluation lifecycle; Phase 12 adds execution details."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
