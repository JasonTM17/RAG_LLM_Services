"""Alembic migration environment (async template).

The database URL is injected from application settings at runtime; it is
never written to this tree and never printed to logs (the sqlalchemy.engine
logger is held at WARN in alembic.ini and no engine sets ``echo=True``).
"""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

import rag_llm_services_api.db.models  # noqa: F401 - registers models on Base.metadata
from rag_llm_services_api.core.config import get_settings
from rag_llm_services_api.db.base import Base

# The Alembic Config object, which provides access to values within the .ini file.
config = context.config

# Interpret the config file for Python logging only when one is configured.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Inject the database URL from application settings; the ini file carries no
# credentials. ConfigParser interpolation treats "%" specially, so percent
# signs (e.g. from percent-encoded URL credentials) must be doubled.
url = get_settings().database.url
config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))

# Model metadata used by autogenerate; domain models register here in Phase 03.
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL and not an Engine, though an
    Engine is acceptable here as well. By skipping the Engine creation we
    don't even need a DBAPI to be available.

    Calls to context.execute() emit the given string to the script output.
    """
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Configure and run migrations on a single synchronous connection."""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Create an async engine from the config and run migrations on it."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode through an async engine."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
