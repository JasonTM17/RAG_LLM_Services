"""Account registration and login endpoints.

Registration and login are the only endpoints that accept credentials; both
sit under the ``/api/v1`` rate limiter plus a dedicated stricter per-route
limit wired in ``main.py``. Wrong-credential responses are identical for
unknown emails and wrong passwords so the endpoint cannot enumerate users.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from rag_llm_services_api.api.v1.schemas.auth import (
    LoginRequest,
    LoginResponse,
    RegisterRequest,
    RegisterResponse,
)
from rag_llm_services_api.core.config import Settings, get_settings
from rag_llm_services_api.core.errors import ConflictError, UnauthorizedError
from rag_llm_services_api.core.passwords import hash_password, verify_password
from rag_llm_services_api.core.tokens import create_access_token
from rag_llm_services_api.db.session import get_session
from rag_llm_services_api.infrastructure.repositories.users import UserRepository

router = APIRouter(prefix="/auth", tags=["auth"])

_CREDENTIAL_ERROR_MESSAGE = "Invalid email or password"


@router.post(
    "/register",
    response_model=RegisterResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new account",
)
async def register_account(
    payload: RegisterRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> RegisterResponse:
    """Create an account; the id becomes the owner_id for all owned data."""
    repo = UserRepository(session)
    existing = await repo.get_by_email(payload.email)
    if existing is not None:
        raise ConflictError("Email is already registered")
    try:
        user = await repo.create(
            email=payload.email,
            password_hash=hash_password(payload.password),
        )
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise ConflictError("Email is already registered") from None
    return RegisterResponse(user_id=user.id, email=user.email)


@router.post(
    "/login",
    response_model=LoginResponse,
    summary="Exchange credentials for an access token",
)
async def login(
    payload: LoginRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> LoginResponse:
    """Verify credentials and mint a stateless JWT access token."""
    repo = UserRepository(session)
    user = await repo.get_by_email(payload.email)
    if user is None or not verify_password(user.password_hash, payload.password):
        raise UnauthorizedError(_CREDENTIAL_ERROR_MESSAGE)
    token = create_access_token(
        user_id=UUID(str(user.id)),
        secret=settings.auth.jwt_secret,
        ttl_minutes=settings.auth.access_token_ttl_minutes,
    )
    return LoginResponse(
        access_token=token,
        expires_in=settings.auth.access_token_ttl_minutes * 60,
    )


__all__ = [
    "router",
]
