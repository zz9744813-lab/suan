"""Worker control routes (spec §15.2)."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.errors import bad_request
from app.models.task import WorkerPolicy, WorkerStatus
from app.schemas import APIResponse, WorkerPolicyRead, WorkerPolicyUpdate, WorkerStatusRead
from app.workers.worker import get_worker


router = APIRouter(prefix="/worker", tags=["worker"])


@router.get("/status", response_model=APIResponse[dict])
async def status() -> APIResponse[dict]:
    worker = get_worker()
    if not worker.is_running:
        await worker.start()
    return {"ok": True, "data": await worker.status()}


@router.get("/multi-status")
async def get_multi_worker_status():
    """Return separate status for Writing/DeepStudy/Discussion/Memory/Model workers.

    Powered by the global ``worker_domain_status`` registry that is
    kept up-to-date by the WorkerController's horizontal partitioning
    (B3 multi-domain scaling).
    """
    from app.workers.worker import worker_domain_status, get_worker

    # Merge the global domain registry with the singleton's top-level
    # status (which carries today_words / today_cost_usd / rate).
    worker_status = await get_worker().status()

    return {
        "writing_worker": {
            **worker_domain_status.get("writing_worker", {}),
            "worker_state": worker_status.get("state", "unknown"),
        },
        "deepstudy_worker": worker_domain_status.get("deepstudy_worker", {}),
        "discussion_worker": worker_domain_status.get("discussion_worker", {}),
        "review_worker": worker_domain_status.get("review_worker", {}),
        "memory_worker": worker_domain_status.get("memory_worker", {}),
        "model_router": worker_domain_status.get("model_router", {}),
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


@router.post("/recover", response_model=APIResponse[dict])
async def recover() -> APIResponse[dict]:
    result = await get_worker().recover_stale_tasks(reason="manual")
    return {"ok": True, "data": {"recovery": result, "status": await get_worker().status()}}


@router.post("/stop", response_model=APIResponse[dict])
async def stop() -> APIResponse[dict]:
    await get_worker().stop()
    return {"ok": True, "data": {"stopped": True, "status": await get_worker().status()}}


# ----------------------------------------------------------------
# 阶段 3.3: Redis 队列 (arq) 概览 / DLQ 读路径
# ----------------------------------------------------------------
@router.get("/queue-summary", response_model=APIResponse[dict])
async def queue_summary() -> APIResponse[dict]:
    """每个 domain 的 pending / running / result 数量, 用于前端展示."""
    from app.queue.dlq import _queue_depth_sync

    summary: dict[str, dict[str, int]] = {}
    for domain in ("writing", "review", "discussion", "memory", "model"):
        try:
            summary[domain] = _queue_depth_sync(domain)
        except Exception as exc:
            summary[domain] = {"pending": 0, "running": 0, "result": 0, "error": str(exc)[:120]}
    return {"ok": True, "data": summary}


@router.get("/dlq", response_model=APIResponse[list])
async def dlq(domain: str = "writing", limit: int = 50) -> APIResponse[list]:
    """读 DLQ. 任务在 arq 跑满重试次数后被 queue_handlers.on_job_max_retries 写进来."""
    from app.queue.dlq import list_dlq

    items = list_dlq(domain=domain, limit=limit)
    return {"ok": True, "data": items}


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
