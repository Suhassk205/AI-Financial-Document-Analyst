"""SQLAlchemy declarative base + shared naming convention.

A consistent naming convention is essential for Alembic autogenerate to produce
stable, predictable constraint/index names across migrations.

`Base.metadata` is the single registry that Alembic targets (see migrations/env.py).
Concrete ORM models are NOT defined here — only the foundation. Models will be
added per phase under `app/models/` and must import this `Base`.
"""

from __future__ import annotations

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

# Stable, deterministic naming for constraints/indexes (Alembic-friendly).
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Project-wide declarative base. All models inherit from this."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)
