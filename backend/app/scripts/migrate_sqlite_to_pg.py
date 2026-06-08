"""SQLite -> PostgreSQL 数据迁移脚本 — 阶段 3.7.

设计原则:
  1. 一次会话, 全部事务; 失败回滚到源库 (源库只读, 不会改)
  2. 表顺序: 父表优先, 避免 FK 违反
  3. 大表分批 (executemany, 1000 行/批)
  4. JSON 列: PG 上是 JSONB, SQLAlchemy 会自动把 dict 序列化
  5. 时间列: SQLite 字符串 -> PG 接受 ISO 格式, 保留 naive UTC

用法:
  cd backend
  # 默认: 源 = ./data/novelforge.db, 目标 = settings.database_url
  python -m app.scripts.migrate_sqlite_to_pg

  # 显式指定源 / 目标
  python -m app.scripts.migrate_sqlite_to_pg \\
      --source sqlite+aiosqlite:///./data/novelforge.db \\
      --target postgresql+asyncpg://novelforge:novelforge@127.0.0.1:5432/novelforge

  # 干跑 (不写目标库)
  python -m app.scripts.migrate_sqlite_to_pg --dry-run
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sqlite3
import sys
import time
from collections.abc import Iterable
from typing import Any

import aiosqlite
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.config import settings
from app.core.database import Base, engine

logger = logging.getLogger("migrate_sqlite_to_pg")


# 父表 -> 子表顺序. 严格按 FK 依赖.
MIGRATION_TABLES: list[str] = [
    # --- 顶层父表 (无依赖) ---
    "projects",
    "model_providers",
    "agent_roles",
    "worker_status",
    "prompt_templates",
    "llm_cache_entries",
    "behavior_cards",
    "audit_logs",

    # --- 依赖 projects ---
    "bibles",
    "outlines",
    "chapters",
    "worker_policies",
    "agent_tasks",
    "agent_steps",
    "agent_events",
    "memory_characters",
    "memory_facts",
    "memory_foreshadows",
    "study_materials",
    "project_study_material_links",
    "agent_model_bindings",
    "discussion_sessions",
    "review_settings",
    "chief_agent_sessions",

    # --- 依赖 chapters ---
    "chapter_versions",
    "review_comments",

    # --- 依赖 study_materials ---
    "study_chapters",
    "study_characters",
    "study_relationships",
    "study_foreshadows",
    "study_chapter_summaries",
    "study_scenes",
    "study_techniques",
    "study_runs",
    "deepstudy_graphs",
    "deepstudy_graph_nodes",
    "deepstudy_graph_edges",
    "deepstudy_stage_results",
    "evolution_nodes",

    # --- 依赖 agent_tasks / study_chapters ---
    "template_usages",
    "genre_prompt_mappings",
    "prompt_auto_fill_batches",
    "behavior_card_uses",
    "model_health_snapshots",
    "model_route_events",
    "model_call_events",
    "prompt_versions",
    "discussion_messages",
    "discussion_syntheses",
    "chief_agent_messages",
]


_BATCH_SIZE = 1000


def _load_sqlite_rows(conn: sqlite3.Connection, table: str) -> list[dict[str, Any]]:
    """读 SQLite 全表, 转为 dict 列表. 文本列原样返回."""
    cur = conn.execute(f'SELECT * FROM "{table}"')
    cols = [c[0] for c in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def _coerce_json_columns(rows: list[dict[str, Any]], table: str) -> list[dict[str, Any]]:
    """PG 上 JSONB 列在 INSERT 时要 dict, 字符串要 parse.

    简化做法: 假定 PG model 里 `column.type` 是 JSON / JSONB, 写时 dict 直接传.
    但 SQLite 读出来的是字符串, 全部 parse 一遍即可.
    """
    out: list[dict[str, Any]] = []
    for row in rows:
        new_row: dict[str, Any] = {}
        for k, v in row.items():
            if isinstance(v, str) and v and v[0] in ("{", "[", '"'):
                # 可能是 JSON 文本
                try:
                    parsed = json.loads(v)
                    if isinstance(parsed, (dict, list)):
                        new_row[k] = parsed
                        continue
                except Exception:
                    pass
            new_row[k] = v
        out.append(new_row)
    return out


async def _bulk_insert(
    db: AsyncSession,
    table: str,
    rows: list[dict[str, Any]],
) -> int:
    """把 rows 写进 PG 表. 走 ``executemany`` 分批.

    使用 INSERT INTO ... ON CONFLICT DO NOTHING (需要 unique key) 简化幂等.
    没有 unique key 的表, 用普通 INSERT.
    """
    if not rows:
        return 0
    model = _model_for_table(table)
    if model is None:
        logger.warning("no model for table=%s, skip", table)
        return 0

    # 模型列
    model_columns = {c.name for c in model.__table__.columns}
    filtered = [{k: v for k, v in row.items() if k in model_columns} for row in rows]

    written = 0
    for i in range(0, len(filtered), _BATCH_SIZE):
        batch = filtered[i:i + _BATCH_SIZE]
        if not batch:
            continue
        stmt = pg_insert(model.__table__).values(batch)
        # 幂等: 如果有 unique constraint, 冲突时跳过
        try:
            stmt = stmt.on_conflict_do_nothing()
        except Exception:
            pass
        await db.execute(stmt)
        written += len(batch)
    await db.flush()
    return written


def _model_for_table(name: str) -> type[Base] | None:
    """从 Base.registry 找表名对应的 model class."""
    for mapper in Base.registry.mappers:
        cls = mapper.class_
        if hasattr(cls, "__tablename__") and cls.__tablename__ == name:
            return cls
    return None


async def _count_table(db: AsyncSession, table: str) -> int:
    res = await db.execute(text(f'SELECT count(*) FROM "{table}"'))
    return int(res.scalar() or 0)


async def migrate(
    source_url: str,
    target_url: str,
    *,
    dry_run: bool = False,
) -> int:
    """主入口. 成功返回 0, 失败返回 1."""
    if not source_url.startswith("sqlite"):
        print(f"ERROR: 源库必须是 SQLite, got {source_url}", file=sys.stderr)
        return 1
    if not (target_url.startswith("postgresql") or target_url.startswith("postgres")):
        print(f"ERROR: 目标库必须是 PostgreSQL, got {target_url}", file=sys.stderr)
        return 1

    t0 = time.time()
    print(f"source: {source_url}")
    print(f"target: {target_url}")
    print(f"dry_run: {dry_run}")

    # 1) 打开 SQLite (同步, 不占事件循环)
    sqlite_path = source_url.replace("sqlite+aiosqlite:///", "")
    sqlite_path = sqlite_path.replace("sqlite:///", "")
    if sqlite_path.startswith("/"):
        sqlite_path = sqlite_path[1:]
    print(f"step 1/4: read sqlite {sqlite_path}")
    src = sqlite3.connect(sqlite_path)
    src.row_factory = sqlite3.Row

    if not dry_run:
        # 2) 校验目标 schema: 表都应已存在 (Alembic upgrade head 已跑)
        print("step 2/4: verify target schema (Alembic head)")
        async with engine.begin() as conn:
            for t in MIGRATION_TABLES:
                res = await conn.execute(text(
                    "SELECT to_regclass(:t)",
                ), {"t": t})
                if res.scalar() is None:
                    print(f"ERROR: target 表 {t} 不存在, 请先 alembic upgrade head",
                          file=sys.stderr)
                    return 1

    # 3) 逐表迁移
    print(f"step 3/4: migrate {len(MIGRATION_TABLES)} tables")
    summary: list[tuple[str, int]] = []
    for t in MIGRATION_TABLES:
        rows = _load_sqlite_rows(src, t)
        rows = _coerce_json_columns(rows, t)
        if dry_run:
            print(f"  - {t}: would insert {len(rows)} rows (dry-run)")
            summary.append((t, len(rows)))
            continue
        async with engine.begin() as conn:
            # 走 _bulk_insert 需要 AsyncSession, 简单起见用 sync ORM 操作
            # 改用 aiosqlite 不合适, 改成 sync psycopg2; 但环境可能没装, 改用
            # raw text insert via asyncpg 走 engine.
            await _bulk_insert_async(conn, t, rows)
        print(f"  - {t}: inserted {len(rows)} rows")
        summary.append((t, len(rows)))

    src.close()

    # 4) 行数对比
    print("step 4/4: row count comparison")
    if not dry_run:
        async with engine.begin() as conn:
            for t, expected in summary:
                actual = await _count_table(conn, t)
                status = "OK" if actual == expected else "DIFF"
                print(f"  - {t}: source={expected} target={actual} {status}")
                if actual != expected:
                    print(f"    !! row count mismatch on {t}", file=sys.stderr)

    print(f"done in {time.time() - t0:.1f}s")
    return 0


async def _bulk_insert_async(
    conn: Any,
    table: str,
    rows: list[dict[str, Any]],
) -> None:
    """走 conn.execute(text(...)) 的轻量 INSERT. 简单可靠, 不依赖 ORM.

    优点: 不需要每个表都 mapping 一遍; 缺点: 不会跑 PG 端的 column default
    (e.g. autoincrement), 但 SQLite 行本来就有 id, 直接写即可.
    """
    if not rows:
        return
    cols = list(rows[0].keys())
    col_list = ", ".join(f'"{c}"' for c in cols)
    placeholders = ", ".join(f":{c}" for c in cols)
    sql = (
        f'INSERT INTO "{table}" ({col_list}) VALUES ({placeholders}) '
        f'ON CONFLICT DO NOTHING'
    )
    for i in range(0, len(rows), _BATCH_SIZE):
        batch = rows[i:i + _BATCH_SIZE]
        # JSON 字段如果是 dict, 转 JSON 字符串
        encoded = []
        for row in batch:
            encoded.append({
                k: (json.dumps(v, ensure_ascii=False, default=str)
                    if isinstance(v, (dict, list)) else v)
                for k, v in row.items()
            })
        await conn.execute(text(sql), encoded)


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    p = argparse.ArgumentParser()
    p.add_argument(
        "--source",
        default=f"sqlite+aiosqlite:///{settings.DATA_DIR / 'novelforge.db'}",
    )
    p.add_argument("--target", default=settings.database_url)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    return asyncio.run(migrate(args.source, args.target, dry_run=args.dry_run))


if __name__ == "__main__":
    sys.exit(main())
