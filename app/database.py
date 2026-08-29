"""数据库引擎与会话。

对应工程方案第 44 节：V1 用 SQLite，V2 迁移 PostgreSQL。
"""

from __future__ import annotations

import os
from collections.abc import Generator
from pathlib import Path

from sqlmodel import Session, SQLModel, create_engine

from .config import get_settings

# SQLite 需要线程共享连接（FastAPI 多线程）
_ENGINE_KWARGS: dict[str, object] = {"connect_args": {"check_same_thread": False}}


def _ensure_sqlite_dir(url: str) -> None:
    """SQLite 文件路径不存在时自动创建父目录。"""
    prefix = "sqlite:///"
    if url.startswith(prefix):
        raw = url[len(prefix):]
        if raw and raw != ":memory:":
            path = Path(raw)
            if not path.is_absolute():
                path = Path.cwd() / path
            path.parent.mkdir(parents=True, exist_ok=True)


def get_engine(url: str | None = None):
    url = url or os.getenv("XUANMIRROR_DB_URL") or get_settings().XUANMIRROR_DB_URL
    _ensure_sqlite_dir(url)
    return create_engine(url, echo=False, **_ENGINE_KWARGS)


engine = get_engine()


def create_db_and_tables(engine_obj=None) -> None:
    """建表。导入 models 包以确保所有表都注册到元数据。"""
    import app.models  # noqa: F401  触发全部表注册

    (engine_obj or engine) and SQLModel.metadata.create_all(engine_obj or engine)


def get_session() -> Generator[Session, None, None]:
    """FastAPI 依赖注入用的会话生成器。"""
    with Session(engine) as session:
        yield session
