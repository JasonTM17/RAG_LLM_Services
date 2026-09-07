"""Schemas for n8n automation reports and evaluation triggers."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

_SECRET_SHAPED_RE = re.compile(
    r"(sk-[A-Za-z0-9]{20,}|gh[po]_[A-Za-z0-9]{30,}|Bearer\s+[A-Za-z0-9._\-]{20,})"
)


def _reject_secret_shaped_values(value: Any) -> Any:
    if isinstance(value, str) and _SECRET_SHAPED_RE.search(value):
        raise ValueError("payload must not contain credential-shaped material")
    if isinstance(value, dict):
        for nested in value.values():
            _reject_secret_shaped_values(nested)
    if isinstance(value, list):
        for nested in value:
            _reject_secret_shaped_values(nested)
    return value


class AutomationReportRequest(BaseModel):
    """Report emitted by a source-controlled n8n workflow."""

    workflow_name: str = Field(min_length=1, max_length=120)
    run_id: str | None = Field(default=None, max_length=120)
    status: Literal["RUNNING", "SUCCEEDED", "FAILED", "SKIPPED"] = "RUNNING"
    summary: str | None = Field(default=None, max_length=1000)
    payload: dict[str, Any] = Field(default_factory=dict)

    @field_validator("payload")
    @classmethod
    def _payload_has_no_secret_shaped_values(cls, value: dict[str, Any]) -> dict[str, Any]:
        return _reject_secret_shaped_values(value)

    @field_validator("summary")
    @classmethod
    def _summary_has_no_secret_shaped_values(cls, value: str | None) -> str | None:
        if value is not None:
            _reject_secret_shaped_values(value)
        return value

    @field_validator("run_id")
    @classmethod
    def _run_id_has_no_secret_shaped_values(cls, value: str | None) -> str | None:
        if value is not None:
            _reject_secret_shaped_values(value)
        return value


class AutomationReportResponse(BaseModel):
    """Persisted workflow report metadata."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    owner_id: UUID
    workflow_name: str
    run_id: str | None = None
    status: str
    summary: str | None = None
    payload_json: dict[str, Any]
    created_at: datetime


class EvaluationCreateRequest(BaseModel):
    """Minimal evaluation trigger request used by n8n until Phase 12."""

    trigger_source: Literal["api", "n8n"] = "api"
    idempotency_key: str | None = Field(default=None, max_length=120)
    workflow_name: str | None = Field(default=None, max_length=120)
    dataset_name: str | None = Field(default="baseline-learning-rag", max_length=120)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("metadata")
    @classmethod
    def _metadata_has_no_secret_shaped_values(cls, value: dict[str, Any]) -> dict[str, Any]:
        return _reject_secret_shaped_values(value)

    @field_validator("idempotency_key", "workflow_name", "dataset_name")
    @classmethod
    def _string_fields_have_no_secret_shaped_values(cls, value: str | None) -> str | None:
        if value is not None:
            _reject_secret_shaped_values(value)
        return value


class EvaluationRunResponse(BaseModel):
    """Evaluation trigger/status response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    owner_id: UUID
    status: str
    idempotency_key: str | None = None
    trigger_source: str
    workflow_name: str | None = None
    dataset_name: str | None = None
    report_path: str | None = None
    error_message: str | None = None
    metadata_json: dict[str, Any]
    created_at: datetime
    updated_at: datetime
