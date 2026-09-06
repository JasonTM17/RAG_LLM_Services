"""Wire-format response envelopes shared across services.

API layers serialize errors as ``{"error": {"code", "message", "request_id"}}``
so clients always receive one stable shape regardless of failure origin.
"""

from __future__ import annotations

from pydantic import BaseModel


class ErrorBody(BaseModel):
    """Machine-readable error details."""

    code: str
    message: str
    request_id: str | None = None


class ErrorEnvelope(BaseModel):
    """Top-level error response wrapper."""

    error: ErrorBody
