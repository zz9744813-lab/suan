"""pytest 配置：用内存 SQLite 隔离测试。

工程方案第 44 节：V1 用 SQLite。
测试环境使用内存库，避免污染 data/xuanmirror.db。
"""

from __future__ import annotations

import importlib

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.database import get_session
from app.main import app

# 触发全部模型注册到 SQLModel.metadata。
# 注意：不能用 `import app.models` —— 那会把局部名字 `app` 重新绑定为
# 包模块，覆盖上面 `from app.main import app` 导入的 FastAPI 实例。
importlib.import_module("app.models")


@pytest.fixture()
def client():
    """带内存数据库的测试客户端。

    StaticPool 是必须的：SQLite 内存库默认每条连接一个独立实例，
    而 TestClient 在 portal 线程执行请求 —— 建表会发生在一个连接上，
    查询却落在另一条空连接上，报 "no such table"。
    StaticPool 强制所有连接复用同一个内存库。
    """
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)

    def _override():
        with Session(engine) as s:
            yield s

    app.dependency_overrides[get_session] = _override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
    engine.dispose()


@pytest.fixture()
def user_id(client: TestClient) -> int:
    """创建一个带出生档案的测试用户。"""
    resp = client.post(
        "/api/users",
        json={
            "user_key": "smoke-user",
            "display_name": "冒烟测试用户",
            "birth_profile": {
                "solar_birth_date": "1990-05-15",
                "solar_birth_time": "14:30",
                "birth_time_known": True,
                "gender": "male",
                "birth_place": "北京",
                "longitude": 116.4,
                "latitude": 39.9,
            },
        },
    )
    assert resp.status_code == 200, resp.text
    return int(resp.json()["user_id"])
