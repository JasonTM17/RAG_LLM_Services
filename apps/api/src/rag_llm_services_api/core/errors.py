"""Error classes re-exported for the API layer.

Deliberate facade: the phase file contract names core/errors.py; canonical
implementation lives in packages/shared (framework-free, reused by the worker
in Phase 08).
"""

from __future__ import annotations

from rag_llm_services_shared.errors import (
    AppError,
    ConfigurationError,
    NotFoundError,
    UnauthorizedError,
    UpstreamUnavailableError,
    ValidationError,
)

__all__ = [
    "AppError",
    "ConfigurationError",
    "NotFoundError",
    "UnauthorizedError",
    "UpstreamUnavailableError",
    "ValidationError",
]
