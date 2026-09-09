"""Rate limiting primitives and ASGI middleware."""

from __future__ import annotations

import hashlib
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Protocol

import redis.asyncio as redis_asyncio
from redis.exceptions import RedisError
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

from rag_llm_services_observability.context import get_request_id
from rag_llm_services_shared.constants import REQUEST_ID_HEADER
from rag_llm_services_shared.envelope import ErrorBody, ErrorEnvelope


@dataclass(frozen=True)
class RateLimitDecision:
    """Result of one rate-limit bucket hit."""

    allowed: bool
    limit: int
    remaining: int
    retry_after_seconds: int


class RateLimitStore(Protocol):
    """Minimal async store contract for a fixed-window rate limiter."""

    async def hit(self, key: str, *, limit: int, window_seconds: int) -> RateLimitDecision:
        """Record one request and return the current decision."""


class InMemoryRateLimitStore:
    """Process-local fixed-window store for tests and local development."""

    def __init__(self, *, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._buckets: dict[str, tuple[float, int]] = {}

    async def hit(self, key: str, *, limit: int, window_seconds: int) -> RateLimitDecision:
        now = self._clock()
        window_start, count = self._buckets.get(key, (now, 0))
        if now - window_start >= window_seconds:
            window_start = now
            count = 0
        count += 1
        self._buckets[key] = (window_start, count)
        remaining = max(limit - count, 0)
        retry_after = max(int(window_seconds - (now - window_start)), 1)
        return RateLimitDecision(
            allowed=count <= limit,
            limit=limit,
            remaining=remaining,
            retry_after_seconds=retry_after,
        )


class RedisRateLimitStore:
    """Redis-backed fixed-window store for production and shared compose runs."""

    def __init__(self, redis_url: str, *, socket_timeout_seconds: float = 1.0) -> None:
        self._redis_url = redis_url
        self._socket_timeout_seconds = socket_timeout_seconds

    async def hit(self, key: str, *, limit: int, window_seconds: int) -> RateLimitDecision:
        client = redis_asyncio.from_url(
            self._redis_url,
            socket_connect_timeout=self._socket_timeout_seconds,
            socket_timeout=self._socket_timeout_seconds,
            decode_responses=True,
        )
        try:
            current = int(await client.incr(key))
            if current == 1:
                await client.expire(key, window_seconds)
            ttl = int(await client.ttl(key))
        finally:
            await client.aclose()
        retry_after = ttl if ttl > 0 else window_seconds
        return RateLimitDecision(
            allowed=current <= limit,
            limit=limit,
            remaining=max(limit - current, 0),
            retry_after_seconds=max(retry_after, 1),
        )


def build_rate_limit_store(backend: str, *, redis_url: str) -> RateLimitStore:
    """Build the configured store, keeping production Redis explicit."""
    if backend == "redis":
        return RedisRateLimitStore(redis_url)
    if backend == "memory":
        return InMemoryRateLimitStore()
    raise ValueError("RATE_LIMIT_BACKEND must be one of: memory, redis")


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Apply a bounded fixed-window rate limit to API routes."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        enabled: bool,
        requests_per_window: int,
        window_seconds: int,
        store: RateLimitStore,
        fail_closed: bool,
        path_prefixes: tuple[str, ...] = ("/api/v1",),
        exempt_path_prefixes: tuple[str, ...] = (
            "/api/v1/ingestion-jobs/queue",
            "/health",
            "/metrics",
            "/docs",
            "/openapi.json",
        ),
        route_limits: Mapping[str, tuple[int, int]] | None = None,
    ) -> None:
        super().__init__(app)
        self._enabled = enabled
        self._requests_per_window = requests_per_window
        self._window_seconds = window_seconds
        self._store = store
        self._fail_closed = fail_closed
        self._path_prefixes = path_prefixes
        self._exempt_path_prefixes = exempt_path_prefixes
        # Exact-path overrides for sensitive endpoints (e.g. /api/v1/auth/*):
        # (requests_per_window, window_seconds), keyed by URL path.
        self._route_limits = dict(route_limits or {})

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if not self._should_limit(request):
            return await call_next(request)

        key = self._key_for(request)
        limit = self._requests_per_window
        window = self._window_seconds
        route_limit = self._route_limits.get(request.url.path)
        if route_limit is not None:
            limit, window = route_limit
            key = f"{key}:{request.url.path}"
        try:
            decision = await self._store.hit(key, limit=limit, window_seconds=window)
        except (OSError, RedisError, RuntimeError, TimeoutError):
            if self._fail_closed:
                return self._error_response(
                    request,
                    status_code=503,
                    code="RATE_LIMIT_UNAVAILABLE",
                    message="Rate limit check is unavailable",
                    retry_after=1,
                )
            response = await call_next(request)
            response.headers["X-RateLimit-Policy"] = "degraded"
            return response

        if not decision.allowed:
            return self._error_response(
                request,
                status_code=429,
                code="RATE_LIMIT_EXCEEDED",
                message="Too many requests",
                retry_after=decision.retry_after_seconds,
                limit=decision.limit,
                remaining=decision.remaining,
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(decision.limit)
        response.headers["X-RateLimit-Remaining"] = str(decision.remaining)
        return response

    def _should_limit(self, request: Request) -> bool:
        path = request.url.path
        if not self._enabled or request.method == "OPTIONS":
            return False
        if any(path.startswith(prefix) for prefix in self._exempt_path_prefixes):
            return False
        return any(path.startswith(prefix) for prefix in self._path_prefixes)

    @staticmethod
    def _bucket_for(path: str) -> str:
        parts = [part for part in path.split("/") if part]
        if len(parts) >= 3 and parts[0] == "api" and parts[1] == "v1":
            return parts[2]
        return "api"

    def _key_for(self, request: Request) -> str:
        client_host = request.client.host if request.client else "unknown"
        raw = f"{client_host}:{request.method}:{self._bucket_for(request.url.path)}"
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        return f"rate_limit:{digest}"

    @staticmethod
    def _error_response(
        request: Request,
        *,
        status_code: int,
        code: str,
        message: str,
        retry_after: int,
        limit: int | None = None,
        remaining: int | None = None,
    ) -> JSONResponse:
        request_id = getattr(request.state, "request_id", None) or get_request_id()
        envelope = ErrorEnvelope(error=ErrorBody(code=code, message=message, request_id=request_id))
        headers = {"Retry-After": str(retry_after)}
        if request_id:
            headers[REQUEST_ID_HEADER] = request_id
        if limit is not None:
            headers["X-RateLimit-Limit"] = str(limit)
        if remaining is not None:
            headers["X-RateLimit-Remaining"] = str(remaining)
        return JSONResponse(status_code=status_code, content=envelope.model_dump(), headers=headers)


__all__ = [
    "InMemoryRateLimitStore",
    "RateLimitDecision",
    "RateLimitMiddleware",
    "RateLimitStore",
    "RedisRateLimitStore",
    "build_rate_limit_store",
]
