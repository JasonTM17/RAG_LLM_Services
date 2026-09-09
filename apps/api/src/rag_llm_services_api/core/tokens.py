"""Stateless JWT access tokens for account authentication.

HS256 only, with pinned issuer/audience and required ``exp``/``sub`` claims.
Tokens carry no roles or scopes: ownership is the ``sub`` UUID, and every
owner-scoped query already filters on it. There is no revocation list; a
compromised token is valid until ``exp`` — rotate ``RAG_AUTH_JWT_SECRET``
to invalidate all outstanding tokens (documented limitation).
"""

from __future__ import annotations

import time
from uuid import UUID

import jwt

from rag_llm_services_api.core.errors import UnauthorizedError

ALGORITHM = "HS256"
ISSUER = "rag-llm-services"
AUDIENCE = "rag-api"


def create_access_token(
    *,
    user_id: UUID,
    secret: str,
    ttl_minutes: int,
    now: float | None = None,
) -> str:
    """Mint a signed access token for ``user_id``.

    ``now`` exists for tests; production callers omit it so tokens use the
    real clock.
    """
    issued_at = int(now if now is not None else time.time())
    payload = {
        "sub": str(user_id),
        "iat": issued_at,
        "exp": issued_at + ttl_minutes * 60,
        "iss": ISSUER,
        "aud": AUDIENCE,
    }
    return jwt.encode(payload, secret, algorithm=ALGORITHM)


def decode_access_token(token: str, *, secret: str) -> UUID:
    """Verify signature, algorithm, issuer, audience, and expiry.

    Every failure path raises :class:`UnauthorizedError` with an identical
    message so tokens leak nothing about why they were rejected. The
    ``algorithms`` pin is deliberate: it closes the algorithm-confusion
    family regardless of the secret's strength.
    """
    try:
        payload = jwt.decode(
            token,
            secret,
            algorithms=[ALGORITHM],
            issuer=ISSUER,
            audience=AUDIENCE,
            options={"require": ["exp", "sub"]},
        )
    except jwt.PyJWTError as exc:
        raise UnauthorizedError("Invalid or expired access token") from exc
    try:
        return UUID(str(payload["sub"]))
    except (KeyError, ValueError) as exc:
        raise UnauthorizedError("Invalid or expired access token") from exc


__all__ = [
    "ALGORITHM",
    "AUDIENCE",
    "ISSUER",
    "create_access_token",
    "decode_access_token",
]
