"""Schemas for account registration and login."""

from __future__ import annotations

import re
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$")
_PASSWORD_MIN_LENGTH = 10


def _normalize_email(value: str) -> str:
    email = value.strip().lower()
    if not _EMAIL_RE.match(email):
        raise ValueError("email must be a valid address")
    return email


def _validate_password(value: str) -> str:
    if len(value) < _PASSWORD_MIN_LENGTH:
        raise ValueError(f"password must be at least {_PASSWORD_MIN_LENGTH} characters")
    return value


class RegisterRequest(BaseModel):
    """Create a new account."""

    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=_PASSWORD_MIN_LENGTH, max_length=128)

    @field_validator("email")
    @classmethod
    def _email_normalised(cls, value: str) -> str:
        return _normalize_email(value)

    @field_validator("password")
    @classmethod
    def _password_long_enough(cls, value: str) -> str:
        return _validate_password(value)


class RegisterResponse(BaseModel):
    """Metadata of the created account."""

    user_id: UUID
    email: str


class LoginRequest(BaseModel):
    """Exchange credentials for an access token."""

    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def _email_normalised(cls, value: str) -> str:
        return _normalize_email(value)


class LoginResponse(BaseModel):
    """Issued access token."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int
