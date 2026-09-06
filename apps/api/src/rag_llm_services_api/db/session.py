"""Async engine and session management for the API.

Engines and session factories are created lazily on first use (no import-time
side effects), cached as module-level singletons, and can be disposed so the
application lifespan or tests can rebuild them cleanly.
"""

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from rag_llm_services_api.core.config import Settings, get_settings

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def build_engine(settings: Settings) -> AsyncEngine:
    """Build a new async engine from the given settings.

    Args:
        settings: Application settings providing ``database.url``.

    Returns:
        A configured ``AsyncEngine`` with connection health checks and a
        bounded pool (5 base connections, 10 overflow).
    """
    return create_async_engine(
        settings.database.url,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
    )


def get_engine(settings: Settings | None = None) -> AsyncEngine:
    """Return the cached engine, building it and the session factory lazily.

    Args:
        settings: Optional settings override used on first build only;
            defaults to ``get_settings()``.

    Returns:
        The process-wide ``AsyncEngine`` singleton.
    """
    global _engine, _sessionmaker
    if _engine is None:
        resolved = settings if settings is not None else get_settings()
        _engine = build_engine(resolved)
        _sessionmaker = async_sessionmaker(_engine, expire_on_commit=False)
    return _engine


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding an ``AsyncSession`` bound to the engine.

    The session is closed when the request finishes; committed objects stay
    populated (``expire_on_commit=False``) after the transaction ends.
    """
    engine = get_engine()
    sessionmaker = _sessionmaker
    if sessionmaker is None:  # defensive: get_engine() populates this
        sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    async with sessionmaker() as session:
        yield session


async def dispose_engine() -> None:
    """Dispose the cached engine and reset the singletons.

    Called on application shutdown or in test teardown so a later call to
    :func:`get_engine` rebuilds against fresh settings.
    """
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _sessionmaker = None
