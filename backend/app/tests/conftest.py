"""conftest.py — pytest 全局 fixture。

策略 (用户 2026-06-07 决定):
- 使用生产 novelforge.db
- session 范围: 开始时跑 reset_test_db (TRUNCATE 不重 seed)
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

import asyncio
import sys
from pathlib import Path

# 让 app.* 可 import
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pytest
import pytest_asyncio
import httpx


@pytest.fixture(scope="session", autouse=True)
def _reset_db_once_per_session():
    """session 范围: pytest 启动前 TRUNCATE 一次, 跑完不重 seed。"""
    from app.scripts.reset_test_db import main as reset_main
    asyncio.run(reset_main())
    yield
    # 跑完不重 seed (用户决定)


@pytest.fixture(autouse=True)
def _reset_db_before_each_test():
    """每个测试前再 TRUNCATE 一次, 防测试之间数据污染。"""
    from app.scripts.reset_test_db import main as reset_main
    asyncio.run(reset_main())
    yield


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
