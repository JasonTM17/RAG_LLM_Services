"""Unit tests for stateless JWT access tokens."""

from __future__ import annotations

import time
import uuid

import jwt
import pytest

from rag_llm_services_api.core.errors import UnauthorizedError
from rag_llm_services_api.core.tokens import (
    ALGORITHM,
    AUDIENCE,
    ISSUER,
    create_access_token,
    decode_access_token,
)


def test_create_and_decode_token_roundtrip() -> None:
    secret = "a" * 32
    user_id = uuid.uuid4()
    token = create_access_token(user_id=user_id, secret=secret, ttl_minutes=60)
    resolved_id = decode_access_token(token, secret=secret)
    assert resolved_id == user_id


def test_decode_token_rejects_expired_token() -> None:
    secret = "a" * 32
    user_id = uuid.uuid4()
    past = time.time() - 3600
    token = create_access_token(user_id=user_id, secret=secret, ttl_minutes=10, now=past)
    with pytest.raises(UnauthorizedError, match="Invalid or expired access token"):
        decode_access_token(token, secret=secret)


def test_decode_token_rejects_wrong_secret() -> None:
    secret_a = "a" * 32
    secret_b = "b" * 32
    user_id = uuid.uuid4()
    token = create_access_token(user_id=user_id, secret=secret_a, ttl_minutes=60)
    with pytest.raises(UnauthorizedError, match="Invalid or expired access token"):
        decode_access_token(token, secret=secret_b)


def test_decode_token_rejects_wrong_issuer() -> None:
    secret = "a" * 32
    user_id = uuid.uuid4()
    payload = {
        "sub": str(user_id),
        "iat": int(time.time()),
        "exp": int(time.time()) + 3600,
        "iss": "wrong-issuer",
        "aud": AUDIENCE,
    }
    token = jwt.encode(payload, secret, algorithm=ALGORITHM)
    with pytest.raises(UnauthorizedError, match="Invalid or expired access token"):
        decode_access_token(token, secret=secret)


def test_decode_token_rejects_wrong_audience() -> None:
    secret = "a" * 32
    user_id = uuid.uuid4()
    payload = {
        "sub": str(user_id),
        "iat": int(time.time()),
        "exp": int(time.time()) + 3600,
        "iss": ISSUER,
        "aud": "wrong-audience",
    }
    token = jwt.encode(payload, secret, algorithm=ALGORITHM)
    with pytest.raises(UnauthorizedError, match="Invalid or expired access token"):
        decode_access_token(token, secret=secret)


def test_decode_token_rejects_tampered_payload() -> None:
    secret = "a" * 32
    user_id = uuid.uuid4()
    token = create_access_token(user_id=user_id, secret=secret, ttl_minutes=60)
    # Tamper with token characters
    tampered = token[:-4] + "xxxx"
    with pytest.raises(UnauthorizedError, match="Invalid or expired access token"):
        decode_access_token(tampered, secret=secret)


def test_decode_token_rejects_missing_sub() -> None:
    secret = "a" * 32
    payload = {
        "iat": int(time.time()),
        "exp": int(time.time()) + 3600,
        "iss": ISSUER,
        "aud": AUDIENCE,
    }
    token = jwt.encode(payload, secret, algorithm=ALGORITHM)
    with pytest.raises(UnauthorizedError, match="Invalid or expired access token"):
        decode_access_token(token, secret=secret)
