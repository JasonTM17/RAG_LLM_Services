"""Error classes re-exported for the API layer.

Deliberate facade: the phase file contract names core/errors.py; canonical
implementation lives in packages/shared (framework-free, reused by the worker
in Phase 08).
"""

from __future__ import annotations

from rag_llm_services_shared.errors import (
    AppError,
    ConfigurationError,
    ConflictError,
    NotFoundError,
    PayloadTooLargeError,
    UnauthorizedError,
    UnsupportedMediaTypeError,
    UpstreamUnavailableError,
    ValidationError,
)


class DuplicateDocumentError(ConflictError):
    """Document with identical content already exists in the target knowledge base."""

    default_code = "DUPLICATE_DOCUMENT"
    default_status = 409


__all__ = [
    "AppError",
    "ConfigurationError",
    "ConflictError",
    "DuplicateDocumentError",
    "NotFoundError",
    "PayloadTooLargeError",
    "UnauthorizedError",
    "UnsupportedMediaTypeError",
    "UpstreamUnavailableError",
    "ValidationError",
]
