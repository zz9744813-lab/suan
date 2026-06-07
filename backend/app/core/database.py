"""Async SQLAlchemy database setup."""
from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import event, text
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


# P-Delete-Preview: SQLite 的 ``PRAGMA foreign_keys`` 默认是 OFF, 跨
# connection 不持久 — reset_test_db 关掉它做 TRUNCATE 后, 后续从池里
# 拿到的 connection 仍是 OFF, 导致 ``ON DELETE SET NULL`` / ``CASCADE``
# 在端点请求里不生效 (DELETE 端点会用 200 回应但事件行的 provider_id
# 没被清). 给每个新 connection 自动打开 FK 约束:
#   - 测试环境: reset_test_db 在自己的 connection 上 OFF 完做 TRUNCATE,
#     那个 connection 关闭时 PRAGMA 也跟着失效, 池里换出来的新
#     connection 进入这个 listener 时被强制 ON.
#   - 生产环境: PRAGMA foreign_keys = ON 是 SQLite 的推荐配置, 不开
#     FK 反而会让 schema 失去保护.
@event.listens_for(engine.sync_engine, "connect")
def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record):
    """新 connection 打开时强制启用 FK 约束 (SQLite only)."""
    try:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.close()
    except Exception:
        # 非 SQLite / 无 cursor 时忽略. SQLAlchemy 在异步引擎里
        # ``engine.sync_engine`` 实际仍跑在同一个进程, 但 listener
        # 对 sqlite3 之外的 dialect 也不会执行 PRAGMA (无副作用).
        pass

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
    # Special marker: ("__new_table__<table_name>", "id", "CREATE TABLE IF NOT EXISTS ...")
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
        # P0-MODEL-FAILOVER: Agent model binding selection fields.
        ("agent_model_bindings", "selection_mode", "VARCHAR(30) DEFAULT 'auto'"),
        ("agent_model_bindings", "auto_strategy", "VARCHAR(40) DEFAULT 'quality_first'"),
        ("agent_model_bindings", "candidate_provider_ids", "JSON"),
        ("agent_model_bindings", "candidate_models_json", "JSON"),
        ("agent_model_bindings", "fallback_candidates_json", "JSON"),
        ("agent_model_bindings", "allow_auto_fallback", "BOOLEAN DEFAULT 1"),
        ("agent_model_bindings", "failure_threshold", "INTEGER DEFAULT 2"),
        ("agent_model_bindings", "cooldown_seconds", "INTEGER DEFAULT 300"),
        ("agent_model_bindings", "locked_reason", "TEXT"),
        ("agent_model_bindings", "last_selected_provider_id", "INTEGER"),
        ("agent_model_bindings", "last_selected_model_name", "VARCHAR(200)"),
        ("agent_model_bindings", "last_selection_reason", "TEXT"),
        ("agent_model_bindings", "last_selection_score", "FLOAT"),
        ("agent_model_bindings", "last_selection_at", "DATETIME"),
        # P0-MODEL-FAILOVER: Provider circuit-breaker and runtime stats.
        ("model_providers", "health_score", "FLOAT DEFAULT 0.75"),
        ("model_providers", "success_rate_1h", "FLOAT DEFAULT 1.0"),
        ("model_providers", "success_rate_24h", "FLOAT DEFAULT 1.0"),
        ("model_providers", "avg_latency_ms", "INTEGER"),
        ("model_providers", "consecutive_failures", "INTEGER DEFAULT 0"),
        ("model_providers", "consecutive_successes", "INTEGER DEFAULT 0"),
        ("model_providers", "circuit_state", "VARCHAR(20) DEFAULT 'closed'"),
        ("model_providers", "circuit_open_until", "DATETIME"),
        ("model_providers", "last_failure_type", "VARCHAR(60)"),
        ("model_providers", "last_failure_message", "TEXT"),
        ("model_providers", "last_success_at", "DATETIME"),
        ("model_providers", "daily_cost_usd", "FLOAT DEFAULT 0.0"),
        ("model_providers", "daily_request_count", "INTEGER DEFAULT 0"),
        ("model_providers", "daily_token_count", "INTEGER DEFAULT 0"),
        ("model_providers", "last_reset_date", "VARCHAR(10)"),
        # P11 (NF2 阶段 1): GenrePromptMapping 扩展字段 — PromptAutoBinder 用
        ("genre_prompt_mappings", "source", "VARCHAR(30) DEFAULT 'manual'"),
        ("genre_prompt_mappings", "confidence_score", "FLOAT"),
        ("genre_prompt_mappings", "auto_bind_reason", "TEXT"),
        ("genre_prompt_mappings", "locked_by_user", "BOOLEAN DEFAULT 0"),
        ("genre_prompt_mappings", "auto_fill_batch_id", "VARCHAR(80)"),
        ("genre_prompt_mappings", "last_effect_score", "FLOAT"),
        ("genre_prompt_mappings", "last_used_at", "DATETIME"),
        # S5-T2: AgentTask 延迟重试字段
        ("agent_tasks", "not_before_at", "DATETIME"),
        # S5-T2: AgentTask 重试 + 回退摘要字段
        ("agent_tasks", "retry_count", "INTEGER DEFAULT 0"),
        ("agent_tasks", "max_retries", "INTEGER DEFAULT 3"),
        ("agent_tasks", "last_failure_type", "VARCHAR(80)"),
        ("agent_tasks", "last_fallback_summary", "JSON"),
        ("__new_table__llm_cache_entries", "id", """CREATE TABLE IF NOT EXISTS llm_cache_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id VARCHAR(120) NOT NULL UNIQUE,
    request_hash VARCHAR(80) NOT NULL UNIQUE,
    provider_id INTEGER,
    provider_name VARCHAR(120),
    model_name VARCHAR(200),
    agent_role_key VARCHAR(80),
    step_key VARCHAR(80),
    request_json JSON,
    response_content TEXT DEFAULT '',
    response_raw JSON,
    response_model VARCHAR(200),
    input_tokens INTEGER DEFAULT 0,
    output_tokens INTEGER DEFAULT 0,
    cost_usd FLOAT DEFAULT 0,
    duration_ms INTEGER DEFAULT 0,
    hit_count INTEGER DEFAULT 0,
    created_at DATETIME NOT NULL DEFAULT (datetime('now')),
    updated_at DATETIME NOT NULL DEFAULT (datetime('now')),
    last_hit_at DATETIME
)"""),
        # P0-observability-rework: ModelCallEvent 新增字段
        ("model_call_events", "event_type", "VARCHAR(50)"),
        ("model_call_events", "event_category", "VARCHAR(50)"),
        ("model_call_events", "level", "VARCHAR(20)"),
        ("model_call_events", "chapter_id", "INTEGER REFERENCES chapters(id) ON DELETE SET NULL"),
        ("model_call_events", "step_key", "VARCHAR(50)"),
        ("model_call_events", "provider_name", "VARCHAR(120)"),
        ("model_call_events", "fallback_from_provider", "VARCHAR(120)"),
        ("model_call_events", "fallback_from_model", "VARCHAR(200)"),
        ("model_call_events", "fallback_to_provider", "VARCHAR(120)"),
        ("model_call_events", "fallback_to_model", "VARCHAR(200)"),
        ("model_call_events", "summary", "TEXT"),
        ("model_call_events", "detail_json", "TEXT"),
        ("model_call_events", "cache_hit", "BOOLEAN"),
        ("model_call_events", "request_id", "VARCHAR(120)"),
        ("model_call_events", "error_code", "VARCHAR(80)"),
        # R28: task center three-layer architecture — AgentTask new columns
        ("agent_tasks", "parent_task_id", "INTEGER"),
        ("agent_tasks", "visibility", "VARCHAR(30) DEFAULT 'user'"),
        ("agent_tasks", "domain", "VARCHAR(50) DEFAULT 'writing'"),
        ("agent_tasks", "task_kind", "VARCHAR(80)"),
        ("agent_tasks", "material_id", "INTEGER"),
        ("agent_tasks", "run_id", "INTEGER"),
        ("agent_tasks", "stage_key", "VARCHAR(80)"),
        ("agent_tasks", "progress_current", "INTEGER DEFAULT 0"),
        ("agent_tasks", "progress_total", "INTEGER DEFAULT 0"),
        ("agent_tasks", "display_title", "VARCHAR(240)"),
        ("agent_tasks", "summary_json", "JSON"),
        ("agent_tasks", "lease_owner", "VARCHAR(120)"),
        ("agent_tasks", "lease_expires_at", "DATETIME"),
        ("agent_tasks", "last_heartbeat_at", "DATETIME"),
        ("agent_tasks", "correlation_id", "VARCHAR(120)"),
        # AgentStep: is_mock flag for mock model steps.
        ("agent_steps", "is_mock", "BOOLEAN DEFAULT 0"),
        # GraphEdge: count column for dedup tracking.
        ("graph_edges", "count", "INTEGER DEFAULT 1"),
        # Project-Study boundary: new link table.
        ("__new_table__project_study_material_links", "id", """CREATE TABLE IF NOT EXISTS project_study_material_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    material_id INTEGER NOT NULL,
    link_type VARCHAR(50) DEFAULT 'reference',
    weight FLOAT DEFAULT 1.0,
    enabled BOOLEAN DEFAULT TRUE,
    created_at DATETIME NOT NULL DEFAULT (datetime('now')),
    updated_at DATETIME NOT NULL DEFAULT (datetime('now')),
    UNIQUE(project_id, material_id)
)"""),
        # B1: unify old behavior_patterns → behavior_cards
        ("behavior_cards", "source_pattern_id", "INTEGER"),
        # DeepStudy knowledge graph — two-layer graph persistence
        ("__new_table__deepstudy_graphs", "id", """CREATE TABLE IF NOT EXISTS deepstudy_graphs (
    id INTEGER PRIMARY KEY AUTOINCREMENT, material_id INTEGER NOT NULL UNIQUE,
    status VARCHAR(40) NOT NULL DEFAULT 'not_started', graph_version INTEGER DEFAULT 1,
    node_count INTEGER DEFAULT 0, edge_count INTEGER DEFAULT 0,
    character_count INTEGER DEFAULT 0, location_count INTEGER DEFAULT 0,
    faction_count INTEGER DEFAULT 0, item_count INTEGER DEFAULT 0,
    event_count INTEGER DEFAULT 0, foreshadow_count INTEGER DEFAULT 0,
    behavior_pattern_count INTEGER DEFAULT 0, writing_technique_count INTEGER DEFAULT 0,
    layout_json TEXT, stats_json TEXT, last_error TEXT, built_at DATETIME,
    created_at DATETIME NOT NULL DEFAULT (datetime('now')),
    updated_at DATETIME NOT NULL DEFAULT (datetime('now'))
)"""),
        ("__new_table__deepstudy_graph_nodes", "id", """CREATE TABLE IF NOT EXISTS deepstudy_graph_nodes (
    id INTEGER PRIMARY KEY AUTOINCREMENT, material_id INTEGER NOT NULL, node_key VARCHAR(240) NOT NULL,
    node_type VARCHAR(80) NOT NULL, label VARCHAR(240) NOT NULL, summary TEXT,
    importance FLOAT DEFAULT 0.5, confidence FLOAT DEFAULT 0.5,
    first_seen_chapter INTEGER, last_seen_chapter INTEGER, source_stage VARCHAR(80),
    payload_json TEXT, evidence_json TEXT, x FLOAT, y FLOAT,
    created_at DATETIME NOT NULL DEFAULT (datetime('now')),
    updated_at DATETIME NOT NULL DEFAULT (datetime('now')),
    UNIQUE(material_id, node_key)
)"""),
        ("__new_table__deepstudy_graph_edges", "id", """CREATE TABLE IF NOT EXISTS deepstudy_graph_edges (
    id INTEGER PRIMARY KEY AUTOINCREMENT, material_id INTEGER NOT NULL, edge_key VARCHAR(320) NOT NULL,
    source_node_key VARCHAR(240) NOT NULL, target_node_key VARCHAR(240) NOT NULL,
    source_node_id INTEGER, target_node_id INTEGER,
    edge_type VARCHAR(80) NOT NULL, label VARCHAR(160) NOT NULL, summary TEXT,
    direction VARCHAR(30) DEFAULT 'directed', weight FLOAT DEFAULT 0.5, confidence FLOAT DEFAULT 0.5,
    source_stage VARCHAR(80), evidence_json TEXT, payload_json TEXT,
    first_seen_chapter INTEGER, last_seen_chapter INTEGER, occurrence_count INTEGER DEFAULT 1,
    created_at DATETIME NOT NULL DEFAULT (datetime('now')),
    updated_at DATETIME NOT NULL DEFAULT (datetime('now')),
    UNIQUE(material_id, edge_key)
)"""),
        # DeepStudy stage results — per-chapter audit trail
        ("__new_table__deepstudy_stage_results", "id", """CREATE TABLE IF NOT EXISTS deepstudy_stage_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT, run_id INTEGER NOT NULL, material_id INTEGER NOT NULL,
    chapter_id INTEGER, chapter_index INTEGER, stage_key VARCHAR(80) NOT NULL,
    status VARCHAR(30) DEFAULT 'pending', input_snapshot TEXT, output_json TEXT,
    raw_output TEXT, error_message TEXT, provider_name VARCHAR(120), model_name VARCHAR(200),
    input_tokens INTEGER DEFAULT 0, output_tokens INTEGER DEFAULT 0, cost_usd FLOAT DEFAULT 0,
    duration_ms INTEGER DEFAULT 0, retry_count INTEGER DEFAULT 0,
    created_at DATETIME NOT NULL DEFAULT (datetime('now')),
    updated_at DATETIME NOT NULL DEFAULT (datetime('now'))
)"""),
        # P0-Model-Config: binding_mode + locked_* fields
        ("agent_model_bindings", "binding_mode", "VARCHAR(40) DEFAULT 'auto'"),
        ("agent_model_bindings", "locked_provider_id", "INTEGER"),
        ("agent_model_bindings", "locked_model_name", "VARCHAR(200)"),
        ("agent_model_bindings", "lock_reason", "TEXT"),
        ("agent_model_bindings", "locked_by_user", "BOOLEAN DEFAULT 0"),
        ("agent_model_bindings", "allow_fallback", "BOOLEAN DEFAULT 1"),
        ("agent_model_bindings", "allow_auto_switch", "BOOLEAN DEFAULT 1"),
        ("agent_model_bindings", "updated_by", "VARCHAR(120)"),
        # P0-Model-Config: model_health_snapshots table
        ("__new_table__model_health_snapshots", "id", """CREATE TABLE IF NOT EXISTS model_health_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider_id INTEGER NOT NULL, model_name VARCHAR(200) NOT NULL,
    status VARCHAR(40) DEFAULT 'unknown', health_score FLOAT DEFAULT 0,
    success_rate FLOAT DEFAULT 0, error_rate FLOAT DEFAULT 0,
    avg_latency_ms INTEGER DEFAULT 0, p95_latency_ms INTEGER DEFAULT 0,
    last_success_at DATETIME, last_failure_at DATETIME,
    last_error_code VARCHAR(80), last_error_message TEXT,
    supports_text BOOLEAN DEFAULT 1, supports_image BOOLEAN DEFAULT 0,
    supports_video BOOLEAN DEFAULT 0, supports_json BOOLEAN DEFAULT 0,
    supports_stream BOOLEAN DEFAULT 0,
    context_window INTEGER, max_output_tokens INTEGER,
    input_price_per_million FLOAT, output_price_per_million FLOAT,
    rate_limited_until DATETIME, cooldown_until DATETIME,
    probe_count INTEGER DEFAULT 0, consecutive_failures INTEGER DEFAULT 0,
    created_at DATETIME NOT NULL DEFAULT (datetime('now')),
    updated_at DATETIME NOT NULL DEFAULT (datetime('now')),
    UNIQUE(provider_id, model_name)
)"""),
        # P0-Model-Config: model_route_events table
        ("__new_table__model_route_events", "id", """CREATE TABLE IF NOT EXISTS model_route_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER, step_id INTEGER,
    agent_role_key VARCHAR(120) NOT NULL,
    binding_mode VARCHAR(40) NOT NULL, strategy VARCHAR(80),
    selected_provider_id INTEGER, selected_model_name VARCHAR(200),
    attempted_provider_id INTEGER, attempted_model_name VARCHAR(200),
    route_reason VARCHAR(120) NOT NULL,
    locked BOOLEAN DEFAULT 0, fallback_used BOOLEAN DEFAULT 0, fallback_reason TEXT,
    health_score FLOAT, latency_ms INTEGER,
    error_code VARCHAR(80), error_message TEXT,
    created_at DATETIME NOT NULL DEFAULT (datetime('now'))
)"""),
    ]
    async with engine.begin() as conn:
        for table, column, ddl in _COLUMN_BACKFILLS:
            if table.startswith("__new_table__"):
                # Special marker for new-table creation (idempotent).
                await conn.execute(text(ddl))
            else:
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
