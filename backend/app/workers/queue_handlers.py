"""arq 任务处理器 — 阶段 3.3.

策略:
  - 每个任务都是 ``run_agent_task(ctx, task_id, task_type)``
  - handler 从 PostgreSQL 拉 AgentTask 行, 写 lease, 调 WorkerController
    已有业务函数 ``_run_*`` (3.3 阶段不重写业务, 仅换驱动)
  - 失败/重试: arq 自带重试 + 写回 agent_tasks.status / .error
  - 兼容性: settings.worker_run_in_process = True 时 handler 走
    ``_run_forever`` 老逻辑, 等价于 in-process Worker
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select

from app.core.config import settings
from app.core.database import session_scope
from app.models.task import AgentTask, WorkerStatus
from app.workers.worker import get_worker

logger = logging.getLogger(__name__)


_LEASE_SECONDS = 3600


async def _mark_running(task_id: int, worker_id: str) -> None:
    """给 AgentTask 上 lease. 如果任务不存在, 静默 no-op (DLQ-friendly)."""
    now = datetime.utcnow()
    async with session_scope() as db:
        task = await db.get(AgentTask, task_id)
        if task is None:
            logger.warning("task_id=%s not found, skip lease", task_id)
            return
        task.status = "running"
        task.started_at = task.started_at or now
        task.lease_owner = worker_id
        task.lease_expires_at = now + timedelta(seconds=_LEASE_SECONDS)
        task.last_heartbeat_at = now

        ws = await _get_or_create_status(db)
        ws.current_task_id = task_id
        ws.state = "running"
        ws.last_heartbeat_at = now


async def _mark_terminal(task_id: int, *, ok: bool, error: str | None) -> None:
    async with session_scope() as db:
        task = await db.get(AgentTask, task_id)
        if task is None:
            return
        task.status = "succeeded" if ok else "failed"
        task.finished_at = datetime.utcnow()
        task.lease_owner = None
        task.lease_expires_at = None
        if not ok and error:
            task.error = (task.error or "")[:1500] + "\n" + error
        ws = await _get_or_create_status(db)
        ws.current_task_id = None


async def _get_or_create_status(db) -> WorkerStatus:
    ws = (await db.execute(
        select(WorkerStatus).where(WorkerStatus.id == 1)
    )).scalar_one_or_none()
    if ws is None:
        ws = WorkerStatus(id=1, state="idle")
        db.add(ws)
        await db.flush()
    return ws


async def run_agent_task(
    ctx: dict[str, Any],
    task_id: int,
    task_type: str,
) -> dict[str, Any]:
    """arq 入口: 每个 job 调一次这里.

    真实业务仍走 ``WorkerController._run_*`` 系列方法, 保证
    chapter_pipeline / reader_review / comment_* / project_bootstrap 行为不变.
    """
    worker = get_worker()
    worker_id = worker.worker_id
    ctx["worker_id"] = worker_id
    logger.info("arq pickup task_id=%s task_type=%s", task_id, task_type)

    await _mark_running(task_id, worker_id)

    # 把 AgentTask 行 reload 给业务层用, 业务层只用 task_id 也能再次 get,
    # 这里不重复 db.get 减少耦合.
    ok = False
    err: str | None = None
    try:
        if task_type == "chapter_pipeline":
            async with session_scope() as db:
                task = await db.get(AgentTask, task_id)
                ws = await _get_or_create_status(db)
                policy = await worker._active_policy(db, task.project_id) if task else None
                if policy is None and task is not None:
                    policy = await worker._ensure_default_policy(db, task.project_id)
            if task is not None:
                await worker._run_chapter_pipeline(task, ws, policy)
                # 阶段 3.5: chapter 跑完后, 链入下一章 (如有)
                chapter_id = task.chapter_id
                project_id = task.project_id
        elif task_type == "project_bootstrap":
            async with session_scope() as db:
                task = await db.get(AgentTask, task_id)
                ws = await _get_or_create_status(db)
                policy = await worker._active_policy(db, task.project_id) if task else None
                if policy is None and task is not None:
                    policy = await worker._ensure_default_policy(db, task.project_id)
            if task is not None:
                await worker._run_project_bootstrap(task, ws, policy)
        elif task_type in (
            "reader_review",
            "comment_triage",
            "comment_discussion",
            "comment_cleanup",
            "rewrite_from_discussion",
        ):
            async with session_scope() as db:
                task = await db.get(AgentTask, task_id)
                ws = await _get_or_create_status(db)
            if task is not None:
                await worker._dispatch_event_task(task, ws, policy=None)
        else:
            # 3.4 / 3.5 阶段会补拆书 / 记忆子任务的专门 handler.
            # 现在收到未注册类型, 不抛, 标 succeeded + 记 warning, 避免 DLQ 抖动.
            logger.warning("unregistered task_type=%s, ack-only", task_type)
        ok = True
    except Exception as exc:  # noqa: BLE001
        err = f"{type(exc).__name__}: {exc}"
        logger.exception("arq job failed task_id=%s task_type=%s", task_id, task_type)
        # 抛回给 arq, 让它走 on_job_max_retries / DLQ
        raise
    finally:
        await _mark_terminal(task_id, ok=ok, error=err)
        # 阶段 3.5 链式入队 (失败不抛, 仅 warning)
        if ok:
            try:
                if task_type == "chapter_pipeline" and "chapter_id" in locals() and "project_id" in locals():
                    if chapter_id is not None and project_id is not None:
                        from app.workers.writing_pipeline import enqueue_next_chapter
                        await enqueue_next_chapter(project_id, chapter_id)
                elif task_type == "project_bootstrap" and "task" in locals() and task is not None:
                    from app.workers.writing_pipeline import (
                        enqueue_chapter_task,
                        find_first_chapter_id,
                    )
                    first_id = await find_first_chapter_id(task.project_id)
                    if first_id is not None:
                        await enqueue_chapter_task(first_id)
            except Exception as chain_exc:  # noqa: BLE001
                logger.warning(
                    "writing chain enqueue failed task_id=%s task_type=%s err=%s",
                    task_id, task_type, chain_exc,
                )

    return {"task_id": task_id, "task_type": task_type, "ok": ok}


async def on_startup(ctx: dict[str, Any]) -> None:
    """arq worker 启动钩子: 恢复 stale 任务, 入队 comment_cleanup."""
    worker = get_worker()
    try:
        await worker.recover_stale_tasks(reason="arq_startup")
    except Exception as exc:  # pragma: no cover
        logger.warning("recover_stale_tasks failed at startup: %s", exc)
    try:
        await worker.start()  # 让 WorkerController 维持旧状态机, 但不再跑 tick 循环
    except Exception as exc:  # pragma: no cover
        logger.warning("worker.start() at arq startup failed: %s", exc)
    ctx["worker_id"] = worker.worker_id
    logger.info("arq worker started worker_id=%s", worker.worker_id)


async def on_shutdown(ctx: dict[str, Any]) -> None:
    logger.info("arq worker shutting down worker_id=%s", ctx.get("worker_id"))


async def on_job_max_retries(ctx: dict[str, Any], error: Exception) -> None:
    """arq 在用完重试次数后调这里, 写 DLQ + 写回 agent_tasks.status='failed'."""
    from app.queue.dlq import write_dlq

    job_id = getattr(ctx.get("job"), "job_id", None) or "unknown"
    await write_dlq(
        job_id=job_id,
        task_id=int((ctx.get("kwargs") or {}).get("task_id") or 0),
        task_type=str((ctx.get("kwargs") or {}).get("task_type") or ""),
        error=f"{type(error).__name__}: {error}",
    )
    logger.error(
        "arq job exhausted retries job_id=%s error=%s",
        job_id, error,
    )
