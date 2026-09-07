"""Health endpoints: process liveness and dependency readiness.

``GET /health/live`` is process-only and must never touch settings-driven
dependencies. ``GET /health/ready`` probes Postgres, Redis, and MinIO
concurrently under a hard per-check timeout so a hanging dependency can never
stall the endpoint beyond the appendix SLO readiness budget. Failure entries
carry only the exception type name: exception text can embed connection URLs
containing passwords and must never reach a response body or a log record.
"""

import asyncio
import logging
from typing import Protocol

import httpx
import redis.asyncio
import sqlalchemy
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from rag_llm_services_api.core.config import Settings, get_settings
from rag_llm_services_api.db.session import get_engine

# Appendix SLO readiness p95 < 2s: the per-check timeout must stay well under
# that budget so one slow dependency cannot push readiness past the target.
CHECK_TIMEOUT_SECONDS = 1.5

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


class DependencyCheck(Protocol):
    """A named readiness probe.

    ``check`` returns normally on success and raises on failure; all
    presentation (status mapping, logging) is owned by the readiness route.

    Implementations must be await-cooperative: ``asyncio.wait_for`` can only
    preempt a check at ``await`` points, so a synchronous blocking call inside
    ``check`` would defeat the shared timeout. Wrap blocking SDKs in
    ``asyncio.to_thread`` if they cannot be awaited.
    """

    name: str

    async def check(self) -> None:
        """Run the probe; raise on failure, return on success."""
        ...


class PostgresCheck:
    """Verify the shared async engine can execute a trivial statement."""

    def __init__(self, name: str = "postgres") -> None:
        self.name = name

    async def check(self) -> None:
        engine = get_engine()
        async with engine.connect() as conn:
            await conn.execute(sqlalchemy.text("SELECT 1"))


class RedisCheck:
    """Verify the Redis server answers PING within the shared timeout."""

    def __init__(self, url: str, name: str = "redis") -> None:
        self.url = url
        self.name = name

    async def check(self) -> None:
        async with redis.asyncio.from_url(
            self.url,
            socket_connect_timeout=CHECK_TIMEOUT_SECONDS,
            socket_timeout=CHECK_TIMEOUT_SECONDS,
        ) as client:
            await client.ping()


class MinioCheck:
    """Verify the MinIO liveness endpoint answers with a success status."""

    def __init__(self, endpoint: str, name: str = "minio") -> None:
        self.endpoint = endpoint.rstrip("/")
        self.name = name

    async def check(self) -> None:
        # Bucket existence/creation checks are deferred to Phase 03 (document
        # storage); readiness here only proves the MinIO service is reachable.
        async with httpx.AsyncClient(timeout=CHECK_TIMEOUT_SECONDS) as client:
            response = await client.get(f"{self.endpoint}/minio/health/live")
            response.raise_for_status()


def build_dependency_checks(settings: Settings) -> list[DependencyCheck]:
    """Build readiness probes for every dependency that is configured.

    A check is included only when its setting is set, so an unconfigured
    dependency never degrades readiness.
    """
    checks: list[DependencyCheck] = []
    if settings.database.url:
        checks.append(PostgresCheck(name="postgres"))
    if settings.redis.url:
        checks.append(RedisCheck(url=settings.redis.url, name="redis"))
    if (
        settings.queue.provider == "celery"
        and settings.queue.celery_broker_url
        and settings.queue.celery_broker_url != settings.redis.url
    ):
        checks.append(RedisCheck(url=settings.queue.celery_broker_url, name="celery_broker"))
    if settings.minio.endpoint:
        checks.append(MinioCheck(endpoint=settings.minio.endpoint, name="minio"))
    return checks


def get_ready_checks() -> list[DependencyCheck]:
    """FastAPI dependency supplying the settings-driven readiness probes."""
    return build_dependency_checks(get_settings())


async def _run_check(check: DependencyCheck) -> str:
    """Run one probe under the shared timeout.

    Returns ``"ok"`` or ``"error"`` for the response body. On failure the
    exception type name (never the message) is logged; no exception escapes,
    so one broken dependency cannot fail the whole ``gather``.
    """
    try:
        await asyncio.wait_for(check.check(), timeout=CHECK_TIMEOUT_SECONDS)
    except Exception as exc:  # noqa: BLE001 - any failure degrades readiness only
        error_type = type(exc).__name__
        logger.warning(
            "health check failed",
            extra={"check": check.name, "error_type": error_type},
        )
        return "error"
    return "ok"


@router.get("/health/live")
async def liveness() -> dict[str, str]:
    """Process-only liveness: no settings-driven checks, no dependency I/O."""
    return {"status": "healthy"}


@router.get("/health/ready")
async def readiness(
    checks: list[DependencyCheck] = Depends(get_ready_checks),
) -> JSONResponse:
    """Report aggregate dependency readiness.

    All probes run concurrently. With at least one probe: every ``ok`` maps to
    200 ``healthy``; a mix maps to 503 ``degraded``. With zero probes or all
    probes failing, readiness is 503 ``unhealthy``.
    """
    outcomes = await asyncio.gather(*(_run_check(check) for check in checks))
    check_status = {check.name: outcome for check, outcome in zip(checks, outcomes, strict=True)}

    ok_count = sum(1 for outcome in check_status.values() if outcome == "ok")
    if not check_status or ok_count == 0:
        status_code, status = 503, "unhealthy"
    elif ok_count == len(check_status):
        status_code, status = 200, "healthy"
    else:
        status_code, status = 503, "degraded"

    return JSONResponse(
        status_code=status_code,
        content={"status": status, "checks": check_status},
    )
