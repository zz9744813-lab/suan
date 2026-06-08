"""Writing 流水线 — 阶段 3.5.

提供:
  - enqueue_chapter_task(chapter_id)         把某章对应的 chapter_pipeline 入队
  - enqueue_next_chapter(project_id)         在某章完成后, 找下一章 queued 状态入队
  - enqueue_bootstrap_task(task_id)          把 project_bootstrap 任务入队

设计:
  * chapter_pipeline 是“按 chapter” 跑的, 不是按 project. 上一章
    handler 完成时, 自己再 enqueue 下一章即可.
  * worker.py 已有 ``_run_chapter_pipeline`` 业务, handler 仅做驱动.
"""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select

from app.core.database import session_scope
from app.models.project import Chapter
from app.queue.enqueue import enqueue_task

logger = logging.getLogger(__name__)


CHAPTER_PIPELINE_TASK_TYPE = "chapter_pipeline"
BOOTSTRAP_TASK_TYPE = "project_bootstrap"


async def enqueue_chapter_task(chapter_id: int) -> str | None:
    """入队指定 chapter 的 chapter_pipeline. 返回 job_id 字符串 (来自 enqueue_task)."""
    result = await enqueue_task(
        task_id=chapter_id,
        task_type=CHAPTER_PIPELINE_TASK_TYPE,
        domain="writing",
    )
    return result.job_id


async def enqueue_bootstrap_task(task_id: int) -> str | None:
    result = await enqueue_task(
        task_id=task_id,
        task_type=BOOTSTRAP_TASK_TYPE,
        domain="writing",
    )
    return result.job_id


async def find_next_chapter_id(project_id: int, current_chapter_id: int) -> int | None:
    """找出当前 chapter 之后, 下一个 status='queued' 的 chapter.

    返回 ``chapter_id`` 或 ``None`` (无下一章, 整书跑完).
    """
    async with session_scope() as db:
        cur = await db.get(Chapter, current_chapter_id)
        if cur is None:
            return None
        row = (await db.execute(
            select(Chapter)
            .where(
                Chapter.project_id == project_id,
                Chapter.chapter_no > cur.chapter_no,
                Chapter.status == "queued",
            )
            .order_by(Chapter.chapter_no.asc())
            .limit(1)
        )).scalar_one_or_none()
        return row.id if row is not None else None


async def enqueue_next_chapter(project_id: int, current_chapter_id: int) -> int | None:
    """给某项目当前章跑完后, 入队下一章.

    找不到下一章就返回 None, 不报错.
    """
    next_id = await find_next_chapter_id(project_id, current_chapter_id)
    if next_id is None:
        logger.info(
            "writing chain: no next chapter project_id=%s after chapter_id=%s",
            project_id, current_chapter_id,
        )
        return None
    await enqueue_chapter_task(next_id)
    logger.info(
        "writing chain: enqueued next chapter project_id=%s chapter_id=%s",
        project_id, next_id,
    )
    return next_id


async def find_first_chapter_id(project_id: int) -> int | None:
    """项目第一章节 (chapter_no 最小)."""
    async with session_scope() as db:
        row = (await db.execute(
            select(Chapter)
            .where(Chapter.project_id == project_id)
            .order_by(Chapter.chapter_no.asc())
            .limit(1)
        )).scalar_one_or_none()
        return row.id if row is not None else None
