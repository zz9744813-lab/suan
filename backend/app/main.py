"""NovelForge 2.0 — FastAPI application entry."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.database import init_db
from app.core.errors import APIError
from app.core.events import Event, event_bus
from app.routers import (
    agent_memory,
    agent_roles,
    audit,
    behavior,
    behavior_card,
    chapters,
    chief_agent,
    deepstudy,
    discussion,
    discussion_trace,
    events,
    genre_prompts,
    graph,
    graphs as graphs_router,
    memory,
    model_observability,
    model_control,
    models,
    project_memory,
    projects,
    prompt_matrix,
    prompts,
    reviews,
    search,
    study,
    tasks,
    worker,
)
from app.seed import seed


@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup
    await init_db()
    await seed()
    await event_bus.publish(Event(event_type="app.ready", payload={
        "app": settings.app_name, "version": settings.app_version,
    }))
    yield
    # shutdown — 阶段 3.6
    # 1) 关掉 in-process Worker (如果存在). 默认 worker_run_in_process=False,
    #    业务侧不再持有 WorkerController, 这里走 try/except 兼容.
    try:
        from app.workers.worker import get_worker
        await get_worker().stop()
    except Exception:
        pass
    # 2) 关掉 Redis 异步连接池
    try:
        from app.queue.redis_client import close_async_pool, close_sync_redis
        await close_async_pool()
        close_sync_redis()
    except Exception:
        pass
    # 3) 释放 SQLAlchemy engine 池
    try:
        from app.core.database import engine
        await engine.dispose()
    except Exception:
        pass


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(APIError)
async def api_error_handler(request: Request, exc: APIError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "ok": False,
            "error": {
                "type": exc.error_type,
                "message": exc.message,
                "suggestion": exc.suggestion,
                "details": exc.details,
            },
        },
    )


@app.get("/")
async def root() -> dict:
    return {
        "ok": True,
        "data": {
            "name": settings.app_name,
            "version": settings.app_version,
            "api_prefix": settings.api_prefix,
        },
    }


@app.get("/health")
async def health() -> dict:
    return {"ok": True, "data": {"status": "ok", "version": settings.app_version}}


# ----- Mount routers under /api -----
PREFIX = settings.api_prefix
for r in (projects.router, chapters.router, tasks.router, prompts.router,
          models.router, model_control.router, worker.router, chief_agent.router, memory.router,
          events.router, study.router, behavior.router, graph.router,
          discussion.router, search.router, deepstudy.router,
          project_memory.router, agent_roles.router, agent_roles.agent_runs_router,
          reviews.router, genre_prompts.router,
          prompt_matrix.router,
          behavior_card.router, behavior_card.cat_router,
          discussion_trace.router,
          agent_memory.router, agent_memory.change_router,
          model_observability.router,
          audit.router,
          graphs_router.router):
    app.include_router(r, prefix=PREFIX)
