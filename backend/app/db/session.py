"""Async database engine + session management.

Provides the async SQLAlchemy engine, a session factory, and a FastAPI dependency
`get_db()` that yields a session per request and guarantees cleanup. This is
dependency-injection friendly: endpoints/services declare `db: AsyncSession =
Depends(get_db)` and never construct engines themselves.

A lightweight `ping()` is exposed for the readiness probe (/ready).
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings

# Single application-wide async engine (connection pool).
engine = create_async_engine(
    settings.database_url,
    echo=settings.db_echo,
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
    pool_pre_ping=True,
)

# Session factory — `expire_on_commit=False` so objects stay usable after commit.
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency: yield a session, always close it."""
    async with AsyncSessionLocal() as session:
        yield session


async def ping() -> bool:
    """Return True if the database answers a trivial query (readiness check)."""
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
    return True
