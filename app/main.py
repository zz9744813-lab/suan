"""玄鉴 XuanMirror —— FastAPI 应用入口。

对应工程方案第 44 节：Python / FastAPI / Pydantic / SQLModel / SQLite(V1)。

安全边界（第 65 节）：
    这是一个传统术数与个人预测实验平台，不是经科学验证的预知系统。
    系统不得：以术数诊断疾病、预测死亡日期、替代医生/律师/财务专业人士、
    鼓励高风险下注、因面部特征推断敏感人格事实。
"""

from __future__ import annotations

import logging
import os
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.database import create_db_and_tables

logger = logging.getLogger("xuanmirror")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    create_db_and_tables()
    logger.info(
        "玄鉴 XuanMirror 启动（env=%s, model=%s, fusion=%s）",
        settings.XUANMIRROR_ENV,
        settings.MODEL_VERSION,
        settings.FUSION_VERSION,
    )

    # 第 58 节：SCHEDULER_ENABLED=true 时启动每日自动闭环。
    # 默认关闭，避免开发环境 23:55 自动跑模型烧 token。
    scheduler = None
    if settings.SCHEDULER_ENABLED:
        from app.database import engine as db_engine
        from app.scheduler import start_scheduler

        scheduler = start_scheduler(db_engine)

    yield

    if scheduler is not None and scheduler.running:
        scheduler.shutdown(wait=False)
    logger.info("玄鉴 XuanMirror 关闭")


app = FastAPI(
    title="玄鉴 XuanMirror",
    description=(
        "个人智能未来预测、验证与自校准系统。\n\n"
        "核心原则：Prediction → Freeze → Reality → Verify → Score → Diagnose → Learn → Predict Again\n\n"
        "**安全边界**：这是一个传统术数与个人预测实验平台，"
        "不是经科学验证的预知系统。不得以术数替代医疗、法律、财务专业判断。"
    ),
    version="0.1.0",
    lifespan=lifespan,
)

# 前端 dev server（Vite 默认 5173）
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ----------------------------------------------------------------------
def _meta_payload() -> dict:
    """安全声明 + 版本元信息（第 65 节：系统必须声明安全边界）。"""
    settings = get_settings()
    return {
        "name": "玄鉴 XuanMirror",
        "version": "0.1.0",
        "principle": "Prediction → Freeze → Reality → Verify → Score → Diagnose → Learn",
        "status": "skeleton",
        "notice": (
            "这是一个传统术数与个人预测实验平台，不是经科学验证的预知系统。"
            "不得以术数替代医疗、法律、财务专业判断（第 65 节）。"
        ),
        "versions": {
            "model": settings.MODEL_VERSION,
            "fusion": settings.FUSION_VERSION,
            "prompt": settings.PROMPT_VERSION,
            "rule": settings.RULE_VERSION,
            "engine": settings.ENGINE_VERSION,
        },
    }


@app.get("/", tags=["meta"])
def root():
    # 有前端构建产物时优先返回前端首页，否则返回 JSON 元信息
    if _frontend_dist is not None:
        from fastapi.responses import FileResponse

        return FileResponse(os.path.join(_frontend_dist, "index.html"))
    return _meta_payload()


@app.get("/health", tags=["meta"])
def health():
    from app.core.base import registry

    return {
        "status": "ok",
        "engines": {
            a.source.value: {
                "engine": a.engine_name,
                "available": a.available,
            }
            for a in registry.all()
        },
    }


# /api 别名：前端 dev server 只代理 /api 前缀，
# 根路径的 / 与 /health 经别名暴露给前端（内容与根路径一致）。
@app.get("/api/health", tags=["meta"], include_in_schema=False)
def health_alias():
    return health()


@app.get("/api/meta", tags=["meta"], include_in_schema=False)
def meta_alias():
    # 始终返回 JSON 安全声明（与根路径不同，根路径在打包后返回前端首页）
    return _meta_payload()


# ----------------------------------------------------------------------
# 路由注册
# ----------------------------------------------------------------------
from app.api.routes import (  # noqa: E402
    analytics,
    predictions,
    system,
)

app.include_router(predictions.router, prefix="/api", tags=["predictions"])
app.include_router(analytics.router, prefix="/api", tags=["analytics"])
app.include_router(system.router, prefix="/api", tags=["system"])


# ----------------------------------------------------------------------
# 前端静态文件挂载（打包成 exe 后，后端直接服务前端，无需 Vite dev server）
# ----------------------------------------------------------------------
def _get_frontend_dist() -> str | None:
    """定位前端构建产物目录（index.html + assets/）。

    打包后从 PyInstaller 的 _MEIPASS 临时目录取；开发时从项目 frontend/dist 取。
    找不到（无构建产物）返回 None，此时后端照常提供纯 API。
    """
    if getattr(sys, "frozen", False):
        candidates = [os.path.join(sys._MEIPASS, "dist")]  # type: ignore[attr-defined]
    else:
        candidates = [
            os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend", "dist"),
        ]
    for d in candidates:
        if os.path.isfile(os.path.join(d, "index.html")):
            return d
    return None


_frontend_dist = _get_frontend_dist()

if _frontend_dist is not None:
    from fastapi.responses import FileResponse
    from fastapi.staticfiles import StaticFiles

    # 静态资源（js/css/图片）按真实文件路径服务
    app.mount(
        "/assets",
        StaticFiles(directory=os.path.join(_frontend_dist, "assets")),
        name="assets",
    )

    # SPA fallback：前端路由（/future、/charts…）都返回 index.html
    @app.get("/{full_path:path}", include_in_schema=False)
    def spa_fallback(full_path: str):
        # 未命中的 API 请求不该落到前端首页，保持 404
        if full_path.startswith("api/"):
            from fastapi import HTTPException

            raise HTTPException(status_code=404, detail="Not Found")
        return FileResponse(os.path.join(_frontend_dist, "index.html"))
