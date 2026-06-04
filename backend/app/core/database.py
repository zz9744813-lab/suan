"""Async SQLAlchemy database setup."""
from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import text
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
    # SQLite-specific: wait up to 30s for another process to
    # release the file lock. Without this, ``database is locked``
    # is raised instantly the moment two processes try to write
    # at the same time (e.g. the uvicorn lifespan startup racing
    # a one-shot CLI script). 30s is generous — the dev DB is
    # tiny and a COMMIT is sub-millisecond.
    connect_args={"check_same_thread": False, "timeout": 30.0},
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
        # P0-MODEL-3: per-model health probe state on the Provider row.
        ("model_providers", "last_health_status", "VARCHAR(20)"),
        ("model_providers", "last_health_message", "TEXT"),
        ("model_providers", "last_health_latency_ms", "INTEGER"),
        ("model_providers", "last_health_model", "VARCHAR(120)"),
        ("model_providers", "last_health_at", "DATETIME"),
        # P15 / P0-HEALTH-1: per-test breakdown + role recommendations.
        # Single JSON blob so the role-binding matrix can colour-code
        # risky bindings without us re-running the probe on every load.
        ("model_providers", "last_health_full", "JSON"),
        # R22: provenance column for auto-extracted foreshadows. Lets the
        # Study page and the graph materialise endpoint filter "things
        # this book produced" without scanning the JSON payload blob.
        ("memory_foreshadows", "source_material_id", "INTEGER"),
        # P0-DeepStudy: book-shelf + DeepStudy coordination fields on
        # the StudyMaterial row. ``study_status`` mirrors the older
        # ``status`` field but with the DeepStudy state machine
        # (empty/uploaded/chapterized/studying/.../completed/failed).
        # The default is "empty"; a one-shot UPDATE below
        # backfills existing rows to "chapterized" if they already
        # have chapters, or "empty" if they don't.
        ("study_materials", "study_status", "VARCHAR(40) DEFAULT 'empty'"),
        ("study_materials", "deepstudy_version", "VARCHAR(40)"),
        ("study_materials", "shelf_category", "VARCHAR(80)"),
        ("study_materials", "cover_theme", "JSON"),
        ("study_materials", "study_progress", "JSON"),
        ("study_materials", "knowledge_score", "FLOAT"),
        ("study_materials", "last_deepstudied_at", "DATETIME"),
        # P6: immutable flag on seed prompt templates so the UI's
        # prompt editor doesn't let users "delete" the bundled
        # reader_/chief_comment prompts by accident.
        ("prompt_templates", "immutable", "BOOLEAN DEFAULT 0"),
    ]
    async with engine.begin() as conn:
        for table, column, ddl in _COLUMN_BACKFILLS:
            await _ensure_column(conn, table, column, ddl)

        # P0-DeepStudy: one-shot backfill for existing StudyMaterial
        # rows. We can only run this after the column exists. We map
        # the old ``status`` to the new ``study_status`` so the
        # library API works on legacy rows:
        #   old "draft"            -> "empty"        (no chapters)
        #   old "ready"            -> "chapterized"  (chapterize done)
        #   old "failed"           -> "failed"       (preserve)
        # Anything else is left as-is so a re-run is a no-op.
        #
        # We also re-fire this for rows where the column backfilled
        # to the "empty" default — those are the existing rows that
        # pre-date the migration and need their legacy ``status``
        # mapped onto the new field. Idempotent: a row whose
        # ``study_status`` is already non-empty (e.g. the user has
        # actually run a DeepStudy pass) keeps its real value.
        await conn.execute(text(
            "UPDATE study_materials SET study_status = CASE "
            "  WHEN status = 'ready' THEN 'chapterized' "
            "  WHEN status = 'failed' THEN 'failed' "
            "  ELSE 'empty' END "
            "WHERE study_status = 'empty' OR study_status IS NULL "
            "  OR study_status = ''"
        ))


async def _ensure_column(conn, table: str, column: str, ddl: str) -> None:
    """Add a column to ``table`` if it doesn't already exist.

    Uses SQLite's ``PRAGMA table_info`` to introspect. ``conn`` is
    a raw async SA connection — we drive ``text()`` directly so the
    migration works for both fresh and existing DBs.
    """
    rows = (await conn.execute(text(f"PRAGMA table_info({table})"))).fetchall()
    existing = {row[1] for row in rows}  # row[1] = column name
    if column in existing:
        return
    await conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))
