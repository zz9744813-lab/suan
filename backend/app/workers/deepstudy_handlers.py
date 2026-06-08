"""DeepStudy arq handler — 阶段 3.4.

执行模型:
  study_deepstudy_dispatch (run_id, 1 job per run)
       ├─ 取 StudyRun, 算 next_stage
       ├─ 入队 study_ds_<stage_key> (run_id)
       └─ 没有 next_stage → 调 _finalize_run → 完结

  study_ds_<stage_key> (run_id, 1 job per stage)
       └─ DeepStudyCoordinatorAgent()._execute_stage(db, run, stage_key)

这样:
  * 每次 job 持有短事务, 不再 1167 章一次 commit
  * 任何 stage 失败 → arq 重试 → 重入
  * 多 run 可并发

写库走 PostgreSQL; lease 由 queue_handlers._mark_running / _mark_terminal
统一管. 这里只负责业务.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

from app.core.database import session_scope
from app.models.study import StudyRun
from app.services.deepstudy.coordinator import DeepStudyCoordinatorAgent
from app.workers.deepstudy_pipeline import (
    enqueue_dispatch,
    enqueue_stage,
    pick_next_stage,
    stage_key_from_task_type,
    stage_task_type,
)

logger = logging.getLogger(__name__)


async def run_deepstudy_dispatch(
    ctx: dict[str, Any],
    task_id: int,
    task_type: str,
    **_kwargs: Any,
) -> dict[str, Any]:
    """dispatch job: 决定下一个 stage, 入队后退出.

    注意: 这里 ``task_id`` 的语义与 agent_tasks 不同 — 业务侧把它当作 run_id.
    之所以复用同一个 enqueue_task, 是为了共用 arq 队列与统计.
    写入 ``dispatch_run_id`` 到 arq 上下文便于观察.
    """
    run_id = int(task_id)
    ctx["dispatch_run_id"] = run_id
    logger.info("deepstudy dispatch run_id=%s", run_id)

    async with session_scope() as db:
        run = await db.get(StudyRun, run_id)
        if run is None:
            logger.warning("dispatch: run_id=%s not found, skip", run_id)
            return {"run_id": run_id, "status": "missing"}
        if run.status in ("succeeded", "failed", "cancelled"):
            logger.info(
                "dispatch: run_id=%s already terminal status=%s, skip",
                run_id, run.status,
            )
            return {"run_id": run_id, "status": run.status}

        progress = dict(run.progress or {}) if isinstance(run.progress, dict) else {}
        completed = list(progress.get("completed_stages", []) or [])

    next_stage = pick_next_stage(completed)
    if next_stage is None:
        # 全部 stage 跑完, 走 finalize
        async with session_scope() as db:
            run = await db.get(StudyRun, run_id)
            if run is None:
                return {"run_id": run_id, "status": "missing"}
            if run.status != "running":
                run.status = "running"
                run.started_at = run.started_at or datetime.now(timezone.utc)
            await DeepStudyCoordinatorAgent()._finalize_run(
                db, run, completed,
            )
        return {"run_id": run_id, "status": "finalized"}

    # 入队单 stage job
    await enqueue_stage(run_id, next_stage)
    return {
        "run_id": run_id,
        "next_stage": next_stage,
        "task_type": stage_task_type(next_stage),
    }


async def run_deepstudy_stage(
    ctx: dict[str, Any],
    task_id: int,
    task_type: str,
    **_kwargs: Any,
) -> dict[str, Any]:
    """单 stage job: 实际跑该 stage, 跑完把 dispatch 再次入队推进."""
    run_id = int(task_id)
    stage_key = stage_key_from_task_type(task_type)
    if stage_key is None:
        logger.error("unknown task_type=%s, skip", task_type)
        return {"run_id": run_id, "stage": None, "status": "unknown_task_type"}

    ctx["stage_run_id"] = run_id
    ctx["stage_key"] = stage_key
    logger.info("deepstudy stage run_id=%s stage=%s", run_id, stage_key)

    # 标 running + 当前 stage (从 study_runs 视角)
    async with session_scope() as db:
        run = await db.get(StudyRun, run_id)
        if run is None:
            logger.warning("stage: run_id=%s not found, skip", run_id)
            return {"run_id": run_id, "stage": stage_key, "status": "missing"}
        if run.status in ("succeeded", "failed", "cancelled"):
            return {"run_id": run_id, "stage": stage_key, "status": run.status}
        if run.status == "queued":
            run.status = "running"
            run.started_at = run.started_at or datetime.now(timezone.utc)
        run.current_stage = stage_key
        await db.flush()
        # 拍快照, handler 用完就 release
        run_id_local = run.id
        material_id = run.material_id

    # 跑 stage
    async with session_scope() as db:
        run = await db.get(StudyRun, run_id_local)
        if run is None:
            return {"run_id": run_id_local, "stage": stage_key, "status": "missing"}
        await DeepStudyCoordinatorAgent()._execute_stage(db, run, stage_key)

    # 跑完, 立即把下一次 dispatch 入队 (推进)
    await enqueue_dispatch(run_id)
    return {
        "run_id": run_id,
        "stage": stage_key,
        "material_id": material_id,
        "status": "stage_done",
    }
