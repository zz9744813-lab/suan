"""Alembic env — 阶段 3.2.

用 SQLAlchemy metadata 作为 single source of truth, 启用 autogenerate.
业务模型集中在 ``app.models``, 通过 ``app.core.database.Base.metadata``
让 Alembic 看到.

注意: 同步模式运行 (alembic CLI 仍是同步 API); DATABASE_URL 走
psycopg2 (PG) 或 sqlite (dev). 走 ``+asyncpg`` 的 URL 会在
``_to_sync_url()`` 里被改写成 ``postgresql+psycopg2://``.
"""
from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# 业务模型都挂在 Base.metadata 上. 引入 models 包让 metadata 完整.
from app.core.database import Base
from app import models  # noqa: F401


def _to_sync_url(url: str) -> str:
    """Alembic CLI 走同步驱动, 把 asyncpg / aiosqlite URL 改写.

    - postgresql+asyncpg://  -> postgresql+psycopg2://
    - sqlite+aiosqlite://     -> sqlite://
    其余原样返回.
    """
    if url.startswith("postgresql+asyncpg://"):
        return "postgresql+psycopg2://" + url[len("postgresql+asyncpg://"):]
    if url.startswith("sqlite+aiosqlite://"):
        # aiosqlite 用 ``/`` 开头表示绝对路径, sqlite 用 ``///``
        return "sqlite://" + url[len("sqlite+aiosqlite://"):]
    return url


config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 业务运行时通过 migrate.py 注入; alembic CLI 走环境变量.
# ini 里的 sqlalchemy.url 是占位符 "driver://...", 需要被覆盖.
raw_url = config.get_main_option("sqlalchemy.url") or ""
if not raw_url or raw_url.startswith("driver://"):
    raw_url = os.environ.get("DATABASE_URL", "")
config.set_main_option("sqlalchemy.url", _to_sync_url(raw_url))

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Emit SQL to stdout instead of connecting to a database."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Connect to the database and run migrations."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section) or {},
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
