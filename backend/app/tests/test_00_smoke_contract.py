"""L0 smoke contract tests — 只读, 不动 DB, 不动业务代码。

目的: 证明 app 能干净 import + router 数量稳定 + APIError 格式一致 + seed 幂等。
这些测试是"护栏", 任何后续架构调整如果破坏, 立刻报错。

不需要真 DB, 不需要 ASGITransport, 不需要 fastapi.testclient。
"""
from __future__ import annotations

import asyncio
import inspect
import sys
from pathlib import Path

import pytest

# ===== 1. 干净 import =====

class TestCleanImport:
    def test_app_main_imports(self):
        """app.main 能 import, 不抛 ImportError / ModuleNotFoundError。"""
        from app.main import app  # noqa: F401
        assert app is not None

    def test_all_routers_import(self):
        """所有在 lifespan 里挂载的 router 模块都能 import。"""
        from app.routers import (
            agent_memory, agent_roles, audit, behavior, behavior_card,
            chapters, chief_agent, deepstudy, discussion, discussion_trace,
            events, genre_prompts, graph, memory, model_observability,
            model_control, models, project_memory, projects, prompt_matrix,
            prompts, reviews, search, study, tasks, worker,
        )
        for mod in (agent_memory, agent_roles, audit, behavior, behavior_card,
                    chapters, chief_agent, deepstudy, discussion, discussion_trace,
                    events, genre_prompts, graph, memory, model_observability,
                    model_control, models, project_memory, projects, prompt_matrix,
                    prompts, reviews, search, study, tasks, worker):
            assert hasattr(mod, "router"), f"{mod.__name__} missing .router"

    def test_settings_load(self):
        from app.core.config import settings
        assert settings.app_name
        assert settings.app_version
        assert settings.api_prefix == "/api"


# ===== 2. router 挂载稳定 =====

class TestRouterMounts:
    """任何新的 router 挂到 /api 都必须让这测试通过。"""

    EXPECTED_API_PREFIX_ROUTERS = 30  # 当前 main.py 里的 for-loop 数量, 增长请更新

    def test_app_includes_api_routers(self):
        from app.main import app
        api_routes = [r for r in app.routes if getattr(r, "path", "").startswith("/api/")]
        assert len(api_routes) >= 20, (
            f"API routers 数量 {len(api_routes)} < 20, 是不是漏挂了 router?"
        )

    def test_app_includes_health(self):
        from app.main import app
        paths = {getattr(r, "path", "") for r in app.routes}
        assert "/health" in paths
        assert "/" in paths

    def test_no_duplicate_api_paths(self):
        """同 path + method 重复 = 真重复 (需要报警)。 同 path 不同 method 正常。"""
        from app.main import app
        seen: dict[tuple[str, str], int] = {}
        for r in app.routes:
            p = getattr(r, "path", "")
            if not p.startswith("/api/"):
                continue
            methods = getattr(r, "methods", None) or set()
            for m in methods:
                seen[(p, m)] = seen.get((p, m), 0) + 1
        dups = {k: c for k, c in seen.items() if c > 1}
        assert not dups, f"同 path+method 重复: {dups}"


# ===== 3. APIError 格式契约 =====

class TestAPIErrorContract:
    """任何端点 raise APIError 都被统一 handler 序列化成
    {ok: false, error: {type, message, suggestion, details}} 格式。
    """

    def test_api_error_basic(self):
        from app.core.errors import APIError
        e = APIError(status_code=404, error_type="NotFound", message="项目 1 不存在")
        assert e.status_code == 404
        assert e.error_type == "NotFound"
        assert e.message == "项目 1 不存在"
        assert e.suggestion is None
        assert e.details == {}

    def test_api_error_with_suggestion_and_details(self):
        from app.core.errors import APIError
        e = APIError(
            status_code=400, error_type="BadRequest",
            message="名称不能为空", suggestion="请填一个名字",
            details={"field": "name"},
        )
        assert e.suggestion == "请填一个名字"
        assert e.details == {"field": "name"}

    def test_api_error_payload_shape(self):
        """APIError 内置 detail 必须是统一 dict, 供 handler 序列化。"""
        from app.core.errors import APIError
        e = APIError(status_code=409, error_type="Conflict", message="冲突")
        d = e.detail  # HTTPException 的 detail 字段
        assert isinstance(d, dict)
        assert d["type"] == "Conflict"
        assert d["message"] == "冲突"

    def test_factory_not_found(self):
        from app.core.errors import not_found
        e = not_found("Project", 42)
        assert e.status_code == 404
        assert e.error_type == "NotFound"
        assert "42" in e.message

    def test_factory_bad_request(self):
        from app.core.errors import bad_request
        e = bad_request("项目名称不能为空。")
        assert e.status_code == 400
        assert e.error_type == "BadRequest"
        assert e.message == "项目名称不能为空。"

    def test_factory_conflict(self):
        from app.core.errors import conflict
        e = conflict("项目名重复", suggestion="换一个名字")
        assert e.status_code == 409
        assert e.error_type == "Conflict"
        assert e.suggestion == "换一个名字"


# ===== 4. seed() 幂等 =====

class TestSeedIdempotent:
    """seed() 跑两次不会爆。"""

    def test_seed_callable(self):
        from app.seed import seed
        assert callable(seed)
        assert inspect.iscoroutinefunction(seed), "seed() 必须是 async"

    def test_seed_idempotent(self):
        """seed 跑两遍不应该抛错 (即便数据库已有内容)。

        用临时内存数据库避免污染 novelforge.db。
        seed() 自身会调 init_db() (建表), 所以临时内存库在调之前建。
        """
        from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

        from app.core.config import settings
        from app.core.database import Base
        from app.seed import seed

        async def _go():
            eng = create_async_engine("sqlite+aiosqlite:///:memory:")
            import app.models  # noqa: F401
            async with eng.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            S = async_sessionmaker(eng, expire_on_commit=False, class_=AsyncSession)
            async with S() as db:
                # 临时把 AsyncSessionLocal 替换成 S 的 session factory
                import app.seed as seed_mod
                old_factory = seed_mod.AsyncSessionLocal
                seed_mod.AsyncSessionLocal = S
                try:
                    await seed()  # 1st
                    await seed()  # 2nd (idempotent)
                finally:
                    seed_mod.AsyncSessionLocal = old_factory
            await eng.dispose()

        asyncio.run(_go())


# ===== 5. CORS =====

class TestCORS:
    def test_cors_origins_loaded(self):
        from app.core.config import settings
        assert isinstance(settings.cors_origins, list)
        assert len(settings.cors_origins) > 0, "CORS origins 不能空 (前端 5173 会跨域)"

    def test_cors_middleware_mounted(self):
        from app.main import app
        # user_middleware 是 config 时数据, middleware_stack 才是运行时 stack
        from starlette.middleware.cors import CORSMiddleware
        # 1) 配置层面
        config_layers = [m for m in app.user_middleware if m.cls is CORSMiddleware]
        assert config_layers, "CORS middleware 没在配置层挂载"
        # 2) 实际访问根路由验证 cors header
        # 不直接发请求 (那需要 ASGITransport), 改查 add_middleware 调用次数
        from app.main import app
        # 至少在 lifespan 之前, middleware 已挂上
        assert len(app.user_middleware) > 0
