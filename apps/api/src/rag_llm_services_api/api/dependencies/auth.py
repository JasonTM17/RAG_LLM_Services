"""Authentication and owner identity dependency."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import Depends, Request

from rag_llm_services_api.core.config import Settings, get_settings
from rag_llm_services_api.core.errors import UnauthorizedError
from rag_llm_services_api.core.tokens import decode_access_token


def get_current_user_id(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
) -> UUID:
    """Resolve the current authenticated user/owner ID.

    A valid ``Authorization: Bearer`` JWT is accepted in every environment
    and its verdict is final: a present-but-invalid Bearer header never falls
    through to dev auth, so a bad token cannot be swapped for a dev header.

    Without a Bearer header:

    - Production fails closed (dev auth is guard-blocked there anyway).
    - In development / test with ``dev_auth.auth_enabled=True`` the legacy
      ``X-User-Id`` / ``X-Owner-Id`` headers apply first, falling back to the
      configured dev user; with neither, raises UnauthorizedError.
    """
    authorization = request.headers.get("authorization")
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
        return decode_access_token(token, secret=settings.auth.jwt_secret)

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
