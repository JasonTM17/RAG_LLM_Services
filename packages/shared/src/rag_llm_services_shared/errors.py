"""Application error hierarchy shared across services.

Every error carries a stable machine-readable ``code`` and an HTTP
``status_code`` so API layers can map errors to wire envelopes without
inspecting exception types. Subclasses only override the class-level
defaults; construction always passes through :class:`AppError`.
"""

from __future__ import annotations


class AppError(Exception):
    """Base error carrying a stable machine code and HTTP status."""

    default_code: str = "INTERNAL_ERROR"
    default_status: int = 500

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        status_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code if code is not None else self.default_code
        self.status_code = status_code if status_code is not None else self.default_status


class ValidationError(AppError):
    """Request payload failed validation."""

    default_code = "VALIDATION_ERROR"
    default_status = 422


class NotFoundError(AppError):
    """Requested resource does not exist."""

    default_code = "NOT_FOUND"
    default_status = 404


class UnauthorizedError(AppError):
    """Missing or invalid credentials."""

    default_code = "UNAUTHORIZED"
    default_status = 401


class ConfigurationError(AppError):
    """Runtime configuration is missing or invalid."""

    default_code = "CONFIG_INVALID"
    default_status = 500


class UpstreamUnavailableError(AppError):
    """An upstream dependency (database, provider, cache) is unavailable."""

    default_code = "UPSTREAM_UNAVAILABLE"
    default_status = 503
