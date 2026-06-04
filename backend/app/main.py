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
    agent_roles,
    behavior,
    chapters,
    chief_agent,
    deepstudy,
    discussion,
    events,
    graph,
    memory,
    models,
    project_memory,
    projects,
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
    # shutdown
    from app.workers.worker import get_worker
    await get_worker().stop()


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
          models.router, worker.router, chief_agent.router, memory.router,
          events.router, study.router, behavior.router, graph.router,
          discussion.router, search.router, deepstudy.router,
          project_memory.router, agent_roles.router, agent_roles.agent_runs_router,
          reviews.router):
    app.include_router(r, prefix=PREFIX)
