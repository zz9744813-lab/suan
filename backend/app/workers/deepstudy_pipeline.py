"""DeepStudy stage 任务网格化 — 阶段 3.4.

提供:
  - STAGE_TASK_TYPE_PREFIX = "study_deepstudy_stage_"
  - stage_key → task_type 映射
  - enqueue_next_stage(run_id)  把当前 run 推进到下一 stage
  - run_stage_job()              实际跑一个 stage 的 job
  - run_dispatch_job()           顶层 dispatcher, 一 run 一 job, 内部循环入队 stage job
"""
from __future__ import annotations

import logging
from typing import Any

from app.queue.enqueue import enqueue_task

logger = logging.getLogger(__name__)

# 必须与 backend/app/services/deepstudy/job_graph.py 的 DEEPSTUDY_DAG 一致.
STAGE_KEYS: tuple[str, ...] = (
    "chapter_profile",
    "entity_extract",
    "event_extract",
    "scene_beat_extract",
    "relationship_analyze",
    "behavior_pattern_mine",
    "technique_mine",
)


def stage_task_type(stage_key: str) -> str:
    """stage_key -> arq task_type.

    避免 arq 的 ``_`` 解析歧义, 用 ``study_ds_`` 短前缀 + 全 stage_key 拼接.
    """
    return f"study_ds_{stage_key}"


def dispatch_task_type() -> str:
    return "study_deepstudy_dispatch"


def is_dispatch_task(task_type: str) -> bool:
    return task_type == dispatch_task_type()


def is_stage_task(task_type: str) -> bool:
    return task_type.startswith("study_ds_")


def stage_key_from_task_type(task_type: str) -> str | None:
    if not task_type.startswith("study_ds_"):
        return None
    return task_type[len("study_ds_"):]


async def enqueue_dispatch(run_id: int, *, delay_seconds: float = 0) -> None:
    """把 (run_id) 当成一个 dispatch 任务塞到 arq.

    dispatch job 会再决定跑哪个 stage, 跑完一个 stage 后再次自入队.
    """
    await enqueue_task(
        task_id=run_id,
        task_type=dispatch_task_type(),
        domain="memory",
        delay_seconds=delay_seconds,
    )


async def enqueue_stage(run_id: int, stage_key: str) -> None:
    """把单 stage 入队."""
    await enqueue_task(
        task_id=run_id,
        task_type=stage_task_type(stage_key),
        domain="memory",
    )


def pick_next_stage(completed_stages: list[str]) -> str | None:
    """顺序 DAG: 拿第一个还没跑完的 stage."""
    done = set(completed_stages or [])
    for key in STAGE_KEYS:
        if key not in done:
            return key
    return None
