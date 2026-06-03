"""Async SQLAlchemy database setup."""
from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    future=True,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency that yields an async session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    """Context manager equivalent of get_db for non-FastAPI code paths."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db() -> None:
    """Create all tables. In production prefer Alembic migrations.

    Round 2 (P0-UI-2/3) added four columns to the ``projects`` table
    (category, sort_order, pinned, last_opened_at). For dev DBs that
    pre-date those columns, ``create_all`` is a no-op for existing
    tables, so we also run an idempotent ``ensure_column`` pass that
    backfills missing columns. SQLite-only — production should
    always use Alembic for schema changes.
    """
    # Import all models so SQLAlchemy sees them before create_all.
    from app import models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Lightweight column-level backfill for SQLite dev DBs.
    # Each entry: (table, column, DDL fragment for the column type).
    _COLUMN_BACKFILLS = [
        ("projects", "category", "VARCHAR(80)"),
        ("projects", "sort_order", "INTEGER DEFAULT 0"),
        ("projects", "pinned", "BOOLEAN DEFAULT 0"),
        ("projects", "last_opened_at", "DATETIME"),
    ]
    async with engine.begin() as conn:
        for table, column, ddl in _COLUMN_BACKFILLS:
            await _ensure_column(conn, table, column, ddl)


async def _ensure_column(conn, table: str, column: str, ddl: str) -> None:
    """Add a column to ``table`` if it doesn't already exist.

    Uses SQLite's ``PRAGMA table_info`` to introspect. ``conn`` is
    a raw async SA connection — we drive ``text()`` directly so the
    migration works for both fresh and existing DBs.
    """
    from sqlalchemy import text

    rows = (await conn.execute(text(f"PRAGMA table_info({table})"))).fetchall()
    existing = {row[1] for row in rows}  # row[1] = column name
    if column in existing:
        return
    await conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))
