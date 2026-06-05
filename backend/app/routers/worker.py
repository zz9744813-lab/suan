"""Worker control routes (spec §15.2)."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.errors import bad_request
from app.models.task import WorkerPolicy, WorkerStatus, AgentTask
from app.models.model_provider import ModelProvider
from app.schemas import APIResponse, WorkerPolicyRead, WorkerPolicyUpdate, WorkerStatusRead
from app.workers.worker import get_worker


router = APIRouter(prefix="/worker", tags=["worker"])


@router.get("/status", response_model=APIResponse[dict])
async def status() -> APIResponse[dict]:
    return {"ok": True, "data": await get_worker().status()}


@router.get("/multi-status")
async def get_multi_worker_status(db: AsyncSession = Depends(get_db)):
    """Return separate status for Writing/DeepStudy/Model workers."""

    # Writing worker status from the singleton
    worker_status = await get_worker().status()

    # DeepStudy: count active study tasks
    deepstudy_running = await db.execute(
        select(func.count(AgentTask.id)).where(
            AgentTask.domain == "deepstudy",
            AgentTask.status == "running",
        )
    )
    deepstudy_active_count = deepstudy_running.scalar() or 0

    # Model router: count providers
    providers_total = await db.execute(
        select(func.count(ModelProvider.id))
    )
    total = providers_total.scalar() or 0
    providers_up = await db.execute(
        select(func.count(ModelProvider.id)).where(
            ModelProvider.enabled.is_(True),
            ModelProvider.circuit_state == "closed",
        )
    )
    up = providers_up.scalar() or 0

    return {
        "writing_worker": {
            "status": worker_status.get("state", "unknown"),
            "current_task": worker_status.get("current_task_id"),
            "uptime_seconds": 0,
        },
        "deepstudy_worker": {
            "status": "running" if deepstudy_active_count > 0 else "idle",
            "current_run": None,
            "uptime_seconds": 0,
        },
        "model_router": {
            "status": "healthy" if up > 0 else "degraded",
            "providers_up": up,
            "providers_total": total,
        },
    }


@router.post("/start", response_model=APIResponse[dict])
async def start() -> APIResponse[dict]:
    await get_worker().start()
    return {"ok": True, "data": {"started": True, "status": await get_worker().status()}}


@router.post("/pause", response_model=APIResponse[dict])
async def pause() -> APIResponse[dict]:
    await get_worker().pause()
    return {"ok": True, "data": {"paused": True, "status": await get_worker().status()}}


@router.post("/resume", response_model=APIResponse[dict])
async def resume() -> APIResponse[dict]:
    await get_worker().resume()
    return {"ok": True, "data": {"resumed": True, "status": await get_worker().status()}}


@router.post("/stop", response_model=APIResponse[dict])
async def stop() -> APIResponse[dict]:
    await get_worker().stop()
    return {"ok": True, "data": {"stopped": True, "status": await get_worker().status()}}


@router.get("/policy", response_model=APIResponse[WorkerPolicyRead])
async def get_default_policy(db: AsyncSession = Depends(get_db)) -> APIResponse[WorkerPolicyRead]:
    # first project's policy as global default
    row = (await db.execute(select(WorkerPolicy).order_by(WorkerPolicy.id.asc()).limit(1))).scalar_one_or_none()
    if row is None:
        # create a stub policy with project_id=0 (unusual but serviceable)
        row = WorkerPolicy(project_id=0, daily_word_goal=0)
        # don't persist project_id=0; just return defaults
        return {"ok": True, "data": WorkerPolicyRead(
            id=0, project_id=0,
            daily_word_goal=row.daily_word_goal,
            daily_budget_usd=row.daily_budget_usd,
            pass_score=row.pass_score,
            max_rewrite_rounds=row.max_rewrite_rounds,
            max_retry_per_task=row.max_retry_per_task,
            consecutive_fail_stop=row.consecutive_fail_stop,
            auto_continue=row.auto_continue,
            discussion_policy=row.discussion_policy,
            max_discussion_per_day=row.max_discussion_per_day,
            max_cost_per_discussion=row.max_cost_per_discussion,
        )}
    return {"ok": True, "data": WorkerPolicyRead.model_validate(row)}
