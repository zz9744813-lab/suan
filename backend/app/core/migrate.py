"""Alembic 桥接 — 让 FastAPI lifespan 与 alembic CLI 共享同一份配置.

阶段 3.2 引入. 后续 3.4 / 3.5 阶段也会用这个模块来跑数据迁移脚本.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

from alembic import command
from alembic.config import Config

logger = logging.getLogger(__name__)

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
ALEMBIC_INI = BACKEND_DIR / "alembic.ini"
ALEMBIC_DIR = BACKEND_DIR / "alembic"


def _build_alembic_config() -> Config:
    cfg = Config(str(ALEMBIC_INI))
    # 强制把 script_location 指向 backend/alembic 目录, 即便 alembic.ini
    # 是从别的 cwd 启动的.
    cfg.set_main_option("script_location", str(ALEMBIC_DIR))
    # 把当前进程的 DATABASE_URL (从 .env 读出来的) 传给 Alembic env.py.
    cfg.set_main_option(
        "sqlalchemy.url",
        os.environ.get("DATABASE_URL") or _sqlite_fallback_url(),
    )
    return cfg


def _sqlite_fallback_url() -> str:
    from app.core.config import settings

    return settings.database_url


async def run_alembic_upgrade(revision: str = "head") -> None:
    """在线程池里跑 ``alembic upgrade``.

    Alembic 的 command 仍是同步 API, 用 ``asyncio.to_thread`` 推出去
    执行, 不阻塞事件循环.
    """
    import asyncio

    cfg = _build_alembic_config()
    logger.info("running alembic upgrade -> %s", revision)

    def _do_upgrade() -> None:
        command.upgrade(cfg, revision)

    await asyncio.to_thread(_do_upgrade)
    logger.info("alembic upgrade done")


def run_alembic_upgrade_sync(revision: str = "head") -> None:
    """同步版本, 给脚本或单进程工具用 (例如数据迁移脚本)."""
    cfg = _build_alembic_config()
    logger.info("running alembic upgrade (sync) -> %s", revision)
    command.upgrade(cfg, revision)
    logger.info("alembic upgrade (sync) done")
