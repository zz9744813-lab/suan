"""入队 API — 业务侧只调这里, 不直接 import arq.

设计原则:
  - 入队尽量短, 失败可重试, 但绝不能阻塞 HTTP 响应
  - 入队失败时, 业务可以降级到 in-process Worker 兼容路径
    (通过 settings.worker_run_in_process 控制)
  - 每个任务带 ``task_id`` (AgentTask.id), handler 通过它回查 DB
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from app.core.config import settings
from app.queue.redis_client import get_async_pool

logger = logging.getLogger(__name__)


# 与 worker.py 里的 SUPPORTED_TASKS 一一对应.
DOMAIN_BY_TASK_TYPE: dict[str, str] = {
    "chapter_pipeline": "writing",
    "project_bootstrap": "writing",
    "reader_review": "review",
    "comment_triage": "discussion",
    "comment_discussion": "discussion",
    "comment_cleanup": "discussion",
    "rewrite_from_discussion": "writing",
    # 拆书 / 记忆的子任务也走统一队列, 避免 3.4 之前拆队列
    "study_character": "memory",
    "study_event": "memory",
    "study_behavior_pattern": "memory",
    "study_bulk_characters": "memory",
    "study_bulk_events": "memory",
    "study_bulk_relationships": "memory",
    "study_bulk_summaries": "memory",
    "study_bulk_techniques": "memory",
    "study_bulk_graph_materialise": "memory",
}


def domain_for_task_type(task_type: str) -> str:
    return DOMAIN_BY_TASK_TYPE.get(task_type, "writing")


@dataclass
class EnqueueResult:
    job_id: str
    queue: str
    domain: str
    enqueued_at: str


async def enqueue_task(
    *,
    task_id: int,
    task_type: str,
    domain: str | None = None,
    delay_seconds: float = 0,
) -> EnqueueResult:
    """把 (task_id, task_type) 入到对应 domain 队列.

    失败时仅记录 warning, 不抛异常 — 业务层可以走 ``worker_run_in_process``
    兼容路径兜底.
    """
    domain = domain or domain_for_task_type(task_type)
    queue_name = f"q:{domain}"
    job_id = f"{task_type}:{task_id}:{uuid.uuid4().hex[:8]}"
    enqueued_at = datetime.now(timezone.utc).isoformat()

    payload = {
        "task_id": task_id,
        "task_type": task_type,
        "enqueued_at": enqueued_at,
    }

    try:
        pool = await get_async_pool()
        await pool.enqueue_job(
            "run_agent_task",
            task_id=task_id,
            task_type=task_type,
            _job_id=job_id,
            _queue=queue_name,
            _defer_by=delay_seconds,
        )
        logger.info(
            "enqueued job=%s task_id=%s task_type=%s domain=%s",
            job_id, task_id, task_type, domain,
        )
    except Exception as exc:
        # 入队失败: 记 warning, 不影响业务主流程
        logger.warning(
            "enqueue failed job=%s task_id=%s task_type=%s err=%s",
            job_id, task_id, task_type, exc,
        )

    return EnqueueResult(
        job_id=job_id,
        queue=queue_name,
        domain=domain,
        enqueued_at=enqueued_at,
    )


async def enqueue_or_fallback(
    *,
    task_id: int,
    task_type: str,
    domain: str | None = None,
) -> EnqueueResult | None:
    """根据 ``settings.worker_run_in_process`` 选择:
      - True:  不入队, 返回 None, 业务方继续走 in-process Worker
      - False: 调 ``enqueue_task``
    """
    if settings.worker_run_in_process:
        return None
    return await enqueue_task(task_id=task_id, task_type=task_type, domain=domain)
