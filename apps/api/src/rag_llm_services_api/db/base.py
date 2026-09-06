"""Declarative base with Alembic-friendly constraint naming.

Owner-scoped domain models arrive in Phase 03; this module is only the
baseline metadata. Deterministic constraint names keep autogenerate diffs
stable and make downgrades targetable.
"""

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

NAMING_CONVENTION: dict[str, str] = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Shared declarative base for all persistence models.

    All ORM models must inherit from this base so they register on a single
    ``MetaData`` that the Alembic environment can autogenerate against.
    """

    metadata = MetaData(naming_convention=NAMING_CONVENTION)
