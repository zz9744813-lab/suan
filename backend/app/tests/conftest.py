"""conftest.py — pytest 全局 fixture。

策略:
- 默认使用隔离测试库 backend/data/pytest/novelforge_pytest.db
- session 范围: 先 init_db 建表, 再跑 reset_test_db (TRUNCATE 不重 seed)
- 提供 AsyncClient 走 lifespan (init_db + seed 不用再跑, 表已建好)
- 提供 db fixture 给直接调 ORM 的测试

不在 conftest 跑 lifespan 的 init_db+seed:
- 跑 init_db 会重复建表 (idempotent 但慢)
- 跑 seed 会重新灌 prompt / model_providers / behavior / review_settings 等
  (跟"不重 seed"冲突)
- 测试用真 DB session + 真 HTTP client, 不需要再 init

如果测试需要 seed 数据 (如 prompt, model provider), 单独 fixture 内手动建。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# 让 app.* 可 import
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

BACKEND_DIR = Path(__file__).resolve().parents[2]
TEST_DATA_DIR = Path(os.environ.get("NOVELFORGE_TEST_DATA_DIR", BACKEND_DIR / "data" / "pytest"))
TEST_DATA_DIR.mkdir(parents=True, exist_ok=True)
TEST_DB = TEST_DATA_DIR / "novelforge_pytest.db"

# Pytest must never mutate the live dev/prod database. Set the env before
# any app.* imports so pydantic-settings builds the engine against the
# isolated test database.
os.environ.setdefault("DATABASE_URL", f"sqlite+aiosqlite:///{TEST_DB.as_posix()}")
os.environ.setdefault("STORAGE_DIR", str(TEST_DATA_DIR / "storage"))
os.environ.setdefault("LOG_DIR", str(TEST_DATA_DIR / "logs"))

import pytest
import pytest_asyncio
import httpx


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _reset_db_once_per_session():
    """session 范围: 使用隔离测试库, 启动前建表并 TRUNCATE 一次。"""
    from app.core.database import init_db
    from app.scripts.reset_test_db import main as reset_main

    await init_db()
    await reset_main(verbose=False)
    yield
    # 跑完不重 seed (用户决定)


@pytest_asyncio.fixture(autouse=True)
async def _reset_db_before_each_test():
    """每个测试前再 TRUNCATE 一次, 防测试之间数据污染。"""
    from app.core.database import engine
    from app.scripts.reset_test_db import main as reset_main

    await engine.dispose()
    await reset_main(verbose=False)
    yield
    await engine.dispose()


@pytest_asyncio.fixture
async def client():
    """AsyncClient 走真 lifespan (ASGITransport 自动触发)。"""
    from app.main import app
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def db():
    """直接给 AsyncSession 给 ORM 测试用。"""
    from app.core.database import AsyncSessionLocal
    async with AsyncSessionLocal() as session:
        yield session
