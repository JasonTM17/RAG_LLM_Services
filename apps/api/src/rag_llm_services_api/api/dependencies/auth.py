"""Authentication and owner identity dependency."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import Depends, Request

from rag_llm_services_api.core.config import Settings, get_settings
from rag_llm_services_api.core.errors import UnauthorizedError


def get_current_user_id(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
) -> UUID:
    """Resolve the current authenticated user/owner ID.

    In development / test environments with dev_auth.auth_enabled=True:
    - Prioritizes 'X-User-Id' header (for multi-tenant test isolation).
    - Falls back to configured settings.dev_auth.user_id.
    - If neither is provided, raises UnauthorizedError.

    In production or when dev auth is disabled:
    - Fails closed with UnauthorizedError.
    """
    if settings.app.env == "production" or not settings.dev_auth.auth_enabled:
        raise UnauthorizedError("Authentication required")

    header_id = request.headers.get("x-user-id") or request.headers.get("x-owner-id")
    if header_id:
        try:
            return UUID(header_id.strip())
        except ValueError as exc:
            raise UnauthorizedError("Invalid user ID header format") from exc

    if settings.dev_auth.user_id is not None:
        return settings.dev_auth.user_id

    raise UnauthorizedError("Development auth is enabled but no user ID is configured or provided")
