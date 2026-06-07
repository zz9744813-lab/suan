"""测试前的 DB 重置工具 — TRUNCATE 所有业务表, 不重新 seed。

用法:
  python -m app.scripts.reset_test_db

策略 (用户 2026-06-07 决定):
- 同生产库 novelforge.db
- 跑测试前: TRUNCATE 所有业务表
- 不重新 seed (测试自己造数据)
- 跑完不重 seed, 不删 .db

保护: 这个脚本单独跑, 不被 conftest 自动调, 因为太危险。
conftest 在 session 范围调它。
"""
from __future__ import annotations

import asyncio
import logging

from sqlalchemy import text

from app.core.database import session_scope

logging.disable(logging.CRITICAL)


# 保留: alembic_version (schema 元数据, 删了会重建)
# TRUNCATE: 一切业务表
KEEP = {"alembic_version", "sqlite_sequence"}


async def main() -> None:
    async with session_scope() as db:
        rows = (await db.execute(text(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ))).all()
        tables = [r[0] for r in rows if r[0] not in KEEP]
        print(f"  准备 TRUNCATE {len(tables)} 表:")
        for t in tables:
            print(f"    - {t}")

        # 关外键, 否则顺序不对会卡
        await db.execute(text("PRAGMA foreign_keys = OFF"))
        for t in tables:
            await db.execute(text(f"DELETE FROM \"{t}\""))
        await db.execute(text("PRAGMA foreign_keys = ON"))

        # 重置 sqlite_sequence (auto-increment 计数)。
        # 某些 SQLite 库如果没有 AUTOINCREMENT 表, sqlite_sequence 不存在。
        seq_exists = (await db.execute(text(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='sqlite_sequence'"
        ))).scalar()
        if seq_exists:
            await db.execute(text("DELETE FROM sqlite_sequence"))

        print(f"  ✓ {len(tables)} 表已清空 (保留 alembic_version)")


if __name__ == "__main__":
    asyncio.run(main())
