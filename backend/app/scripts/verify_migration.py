"""迁移后行数对比 + 抽样校验 — 阶段 3.7.

用法:
  python -m app.scripts.verify_migration

行为:
  1. 读 PG 行数, 跟 source SQLite 行数对比
  2. 抽样 4 张关键表 (projects / study_materials / chapters / agent_tasks)
     拉一行, 打印 id / name / status / created_at, 确认可读
  3. 抽样 1 张 JSON 列 (study_materials.study_progress), 确保 JSONB 可解析
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sqlite3
import sys
from typing import Any

from sqlalchemy import text

from app.core.config import settings
from app.core.database import engine

logger = logging.getLogger("verify_migration")


KEY_TABLES_FOR_SAMPLING = [
    "projects",
    "study_materials",
    "chapters",
    "agent_tasks",
]

JSON_TABLES = [
    ("study_materials", "study_progress"),
    ("agent_tasks", "summary_json"),
    ("agent_tasks", "payload"),
]


def _sqlite_row_count(source_path: str, table: str) -> int:
    conn = sqlite3.connect(source_path)
    cur = conn.execute(f'SELECT count(*) FROM "{table}"')
    n = int(cur.fetchone()[0])
    conn.close()
    return n


async def _pg_row_count(table: str) -> int:
    async with engine.begin() as conn:
        res = await conn.execute(text(f'SELECT count(*) FROM "{table}"'))
        return int(res.scalar() or 0)


async def _pg_sample(table: str, limit: int = 3) -> list[dict[str, Any]]:
    async with engine.begin() as conn:
        res = await conn.execute(
            text(f'SELECT * FROM "{table}" ORDER BY id ASC LIMIT {int(limit)}')
        )
        cols = list(res.keys())
        return [dict(zip(cols, row)) for row in res.fetchall()]


async def verify(source_url: str) -> int:
    if not source_url.startswith("sqlite"):
        print(f"ERROR: 源库必须是 SQLite, got {source_url}", file=sys.stderr)
        return 1
    sqlite_path = source_url.replace("sqlite+aiosqlite:///", "").replace("sqlite:///", "")
    if sqlite_path.startswith("/"):
        sqlite_path = sqlite_path[1:]

    print(f"source: {sqlite_path}")
    print(f"target: {settings.database_url}")

    # 1) 关键表行数对比
    print("step 1/3: row count comparison on key tables")
    diffs = 0
    for t in KEY_TABLES_FOR_SAMPLING:
        src_n = _sqlite_row_count(sqlite_path, t)
        pg_n = await _pg_row_count(t)
        status = "OK" if src_n == pg_n else "DIFF"
        print(f"  - {t}: source={src_n} target={pg_n} {status}")
        if src_n != pg_n:
            diffs += 1

    # 2) 抽样 4 张表各取 3 行
    print("step 2/3: sample rows")
    for t in KEY_TABLES_FOR_SAMPLING:
        samples = await _pg_sample(t, 3)
        print(f"  - {t}: {len(samples)} sample(s)")
        for s in samples:
            keys = ["id", "name", "title", "task_type", "status", "chapter_id", "project_id"]
            slim = {k: s.get(k) for k in keys if k in s}
            print(f"    {slim}")

    # 3) JSON 列抽样解析
    print("step 3/3: JSONB column sanity check")
    for t, col in JSON_TABLES:
        samples = await _pg_sample(t, 5)
        for s in samples:
            raw = s.get(col)
            if raw is None:
                continue
            # 已被 ORM 解码为 dict / str
            if isinstance(raw, str):
                try:
                    json.loads(raw)
                except Exception as exc:
                    print(f"    ! {t}.{col} parse failed: {exc}", file=sys.stderr)
                    diffs += 1
            else:
                # dict / list — 已正确解码
                pass
        print(f"  - {t}.{col}: ok (5 rows)")

    if diffs:
        print(f"!! {diffs} diff(s) found", file=sys.stderr)
        return 1
    print("verify OK")
    return 0


def main() -> int:
    logging.basicConfig(level=logging.INFO)
    p = argparse.ArgumentParser()
    p.add_argument(
        "--source",
        default=f"sqlite+aiosqlite:///{settings.DATA_DIR / 'novelforge.db'}",
    )
    args = p.parse_args()
    return asyncio.run(verify(args.source))


if __name__ == "__main__":
    sys.exit(main())
