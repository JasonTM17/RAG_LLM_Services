"""Unit tests for database engine and session creation.

Verifies that engine construction applies bounded pool settings, health checks,
and connect_timeout=2 without attempting live network connections.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from sqlalchemy.ext.asyncio import AsyncEngine

from rag_llm_services_api.core.config import Settings
from rag_llm_services_api.db.session import build_engine, dispose_engine, get_engine


def test_build_engine_configures_connect_timeout() -> None:
    """build_engine passes connect_args connect_timeout: 2 and pool bounds."""
    settings = Settings(_env_file=None)
    with patch("rag_llm_services_api.db.session.create_async_engine") as mock_create:
        build_engine(settings)
        mock_create.assert_called_once()
        args, kwargs = mock_create.call_args
        assert args[0] == settings.database.url
        assert kwargs["pool_pre_ping"] is True
        assert kwargs["pool_size"] == 5
        assert kwargs["max_overflow"] == 10
        assert kwargs["connect_args"] == {"connect_timeout": 2}


async def test_get_and_dispose_engine() -> None:
    """get_engine caches singleton and dispose_engine resets it."""
    settings = Settings(_env_file=None)
    with patch("rag_llm_services_api.db.session.create_async_engine") as mock_create:
        mock_engine = MagicMock(spec=AsyncEngine)
        mock_engine.dispose = AsyncMock()
        mock_create.return_value = mock_engine

        engine_1 = get_engine(settings)
        engine_2 = get_engine(settings)
        assert engine_1 is engine_2
        assert mock_create.call_count == 1

        await dispose_engine()
        assert get_engine(settings) is not None
        assert mock_create.call_count == 2
        await dispose_engine()
