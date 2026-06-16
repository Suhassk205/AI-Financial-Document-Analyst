"""Async database engine + session management.

Provides the async SQLAlchemy engine, a session factory, and a FastAPI dependency
`get_db()` that yields a session per request and guarantees cleanup. This is
dependency-injection friendly: endpoints/services declare `db: AsyncSession =
Depends(get_db)` and never construct engines themselves.

A lightweight `ping()` is exposed for the readiness probe (/ready).
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.core.logging import get_logger

# Single application-wide async engine (connection pool).
engine = create_async_engine(
    settings.database_url,
    echo=settings.db_echo,
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
    pool_recycle=1800,
    pool_timeout=30,
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


async def verify_database_health() -> None:
    """Startup database health check.

    Verifies that:
      1. The database is reachable
      2. The pgvector ('vector') extension exists
      3. Core tables exist (users, companies, reports, document_chunks)

    Raises ValueError if any checks fail in production. Logs warnings in non-production.
    """
    log = get_logger(__name__)
    try:
        async with engine.connect() as conn:
            # 1. Reachability
            await conn.execute(text("SELECT 1"))

            # 2. Check pgvector extension exists
            res_ext = await conn.execute(
                text("SELECT 1 FROM pg_extension WHERE extname = 'vector'")
            )
            if not res_ext.scalar():
                raise ValueError("pgvector extension ('vector') is not installed in the database.")

            # 3. Check core tables exist
            required_tables = {"users", "companies", "reports", "document_chunks"}
            res_tables = await conn.execute(
                text(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = 'public'"
                )
            )
            existing_tables = {row[0] for row in res_tables.fetchall()}
            missing_tables = required_tables - existing_tables
            if missing_tables:
                raise ValueError(
                    f"Required database tables are missing: {', '.join(missing_tables)}. "
                    "Please run migrations using 'alembic upgrade head'."
                )
        log.info("database.health_check_passed")
    except Exception as exc:
        msg = f"Database health check failed: {exc}"
        log.error("database.health_check_failed", error=str(exc))
        if settings.app_env.value == "production":
            raise ValueError(msg) from exc



# ---------------------------------------------------------------------------
# Synchronous engine/session — used by Celery workers.
# Celery tasks run in a synchronous context; rather than driving the async
# engine across ad-hoc event loops, the worker uses a plain sync session
# (psycopg driver, same as Alembic). The API layer remains fully async.
# ---------------------------------------------------------------------------
sync_engine = create_engine(
    settings.database_url_sync,
    echo=settings.db_echo,
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
    pool_recycle=1800,
    pool_timeout=30,
    pool_pre_ping=True,
)

SyncSessionLocal = sessionmaker(
    bind=sync_engine,
    class_=Session,
    expire_on_commit=False,
    autoflush=False,
)
