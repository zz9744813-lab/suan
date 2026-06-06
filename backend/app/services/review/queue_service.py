"""P6 §5 入队 helper — 把读者评审 / 主 Agent 分流 / 讨论室任务写到 agent_tasks.

P4 worker dispatcher 会按 task_type 拉取并跑. 这里是入队单一入口, 保证:
  1. auto_* 开关遵循 ReviewSettings (用户/章节层事件自动触发)
  2. manual_test / API 触发的也走这个入口, 写明 payload.enqueue_source
  3. Idempotent: 同一 (project_id, chapter_id, task_type) 已有 pending → 跳过
  4. 不在 chapter_pipeline 跟其他任务竞争, worker 已经按 task_type.in_ 分发

API 端点也可以调 (例如 reviews/POST /comments 自动 enqueue triage).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import bad_request
from app.models.comment_review import ReviewSettings
from app.models.task import AgentTask

logger = logging.getLogger(__name__)


# 入队 source — 用于审计 / 测试
ENQUEUE_SOURCE_AUTO_PIPELINE = "auto_pipeline"  # chapter_pipeline 成功后
ENQUEUE_SOURCE_AUTO_COMMENT = "auto_comment"    # POST /comments 成功后
ENQUEUE_SOURCE_WORKER_START = "worker_start"    # worker 启动时 (cleanup)
ENQUEUE_SOURCE_MANUAL_API = "manual_api"        # 手动 API (e.g. POST /runs)


@dataclass
class EnqueueResult:
    """入队结果 — task_id 是新写的行 id (None=跳过/失败)."""

    task_id: int | None
    skipped: bool = False
    skip_reason: str | None = None


class ReviewQueueService:
    """把读者评审/分流/讨论任务入队到 agent_tasks.

    全部方法 idempotent — 同一 (project_id, chapter_id, task_type)
    已存在 pending 任务时, 跳过并返回 skipped=True, 不抛错.
    """

    # ---- 公共: 检查是否已有 pending 任务 ----
    async def _has_pending(
        self,
        db: AsyncSession,
        *,
        task_type: str,
        project_id: int,
        chapter_id: int | None = None,
        session_id: int | None = None,
    ) -> bool:
        q = select(AgentTask).where(
            AgentTask.task_type == task_type,
            AgentTask.project_id == project_id,
            AgentTask.status == "pending",
        )
        if chapter_id is not None:
            q = q.where(AgentTask.chapter_id == chapter_id)
        if session_id is not None:
            q = q.where(AgentTask.payload["session_id"].as_integer() == session_id)
        row = (await db.execute(q.limit(1))).scalar_one_or_none()
        return row is not None

    # ---- §5.3: 章节完成后自动触发 reader_review ----
    async def enqueue_reader_review(
        self,
        db: AsyncSession,
        *,
        project_id: int,
        chapter_id: int,
        trigger: str = "chapter_completed",
        source: str = ENQUEUE_SOURCE_AUTO_PIPELINE,
    ) -> EnqueueResult:
        # auto_reader_review 检查
        if source == ENQUEUE_SOURCE_AUTO_PIPELINE:
            settings = (
                await db.execute(
                    select(ReviewSettings).where(ReviewSettings.project_id == project_id)
                )
            ).scalar_one_or_none()
            if settings is not None and not settings.auto_reader_review:
                return EnqueueResult(
                    task_id=None, skipped=True,
                    skip_reason="auto_reader_review=off",
                )

        if await self._has_pending(
            db, task_type="reader_review",
            project_id=project_id, chapter_id=chapter_id,
        ):
            return EnqueueResult(
                task_id=None, skipped=True,
                skip_reason="已有 pending reader_review 任务",
            )

        task = AgentTask(
            project_id=project_id,
            chapter_id=chapter_id,
            task_type="reader_review",
            status="pending",
            priority=70,  # 比 chapter_pipeline (100) 低, 错峰跑
            payload={
                "trigger": trigger,
                "enqueue_source": source,
            },
        )
        db.add(task)
        await db.flush()
        logger.info(
            "queue: enqueue reader_review project=%s chapter=%s trigger=%s source=%s task_id=%s",
            project_id, chapter_id, trigger, source, task.id,
        )
        return EnqueueResult(task_id=task.id)

    # ---- §5.4: 用户发评论后自动触发主 Agent 分流 ----
    async def enqueue_triage(
        self,
        db: AsyncSession,
        *,
        project_id: int,
        chapter_id: int | None = None,
        source: str = ENQUEUE_SOURCE_AUTO_COMMENT,
    ) -> EnqueueResult:
        if source == ENQUEUE_SOURCE_AUTO_COMMENT:
            settings = (
                await db.execute(
                    select(ReviewSettings).where(ReviewSettings.project_id == project_id)
                )
            ).scalar_one_or_none()
            if settings is not None and not settings.auto_chief_triage:
                return EnqueueResult(
                    task_id=None, skipped=True,
                    skip_reason="auto_chief_triage=off",
                )

        if await self._has_pending(
            db, task_type="comment_triage",
            project_id=project_id, chapter_id=chapter_id,
        ):
            return EnqueueResult(
                task_id=None, skipped=True,
                skip_reason="已有 pending comment_triage 任务",
            )

        task = AgentTask(
            project_id=project_id,
            chapter_id=chapter_id,
            task_type="comment_triage",
            status="pending",
            priority=80,  # 比 reader_review 高一点, 让 triage 早跑
            payload={
                "enqueue_source": source,
            },
        )
        db.add(task)
        await db.flush()
        logger.info(
            "queue: enqueue comment_triage project=%s chapter=%s source=%s task_id=%s",
            project_id, chapter_id, source, task.id,
        )
        return EnqueueResult(task_id=task.id)

    # ---- §4.4: 评论组转讨论, DiscussionBridge 之后跑 participant + synthesis ----
    async def enqueue_comment_discussion(
        self,
        db: AsyncSession,
        *,
        project_id: int,
        session_id: int,
        group_id: int,
    ) -> EnqueueResult:
        if await self._has_pending(
            db, task_type="comment_discussion",
            project_id=project_id, session_id=session_id,
        ):
            return EnqueueResult(
                task_id=None, skipped=True,
                skip_reason="已有 pending comment_discussion 任务",
            )

        task = AgentTask(
            project_id=project_id,
            chapter_id=None,
            task_type="comment_discussion",
            status="pending",
            priority=60,
            payload={
                "session_id": session_id,
                "group_id": group_id,
                "enqueue_source": ENQUEUE_SOURCE_AUTO_PIPELINE,
            },
        )
        db.add(task)
        await db.flush()
        logger.info(
            "queue: enqueue comment_discussion project=%s session=%s group=%s task_id=%s",
            project_id, session_id, group_id, task.id,
        )
        return EnqueueResult(task_id=task.id)

    # ---- §5.5: 定时清理, 启动时入队一次 ----
    async def enqueue_comment_cleanup(
        self,
        db: AsyncSession,
        *,
        retention_days: int = 7,
        source: str = ENQUEUE_SOURCE_WORKER_START,
    ) -> EnqueueResult:
        # 清理任务不绑 project (跨项目), 用 project_id=0 表示"系统级"
        # 但 AgentTask.project_id 是 NOT NULL FK, 用第一个 project 兜底
        if await self._has_pending(db, task_type="comment_cleanup", project_id=0):
            return EnqueueResult(
                task_id=None, skipped=True,
                skip_reason="已有 pending comment_cleanup 任务",
            )

        # 找一个真实 project_id 当 FK 兜底 (cleanup 不跟具体 project 强绑)
        from app.models.project import Project
        proj_row = (
            await db.execute(select(Project).order_by(Project.id.asc()).limit(1))
        ).scalar_one_or_none()
        if proj_row is None:
            return EnqueueResult(
                task_id=None, skipped=True,
                skip_reason="无 project, 无法入队 comment_cleanup",
            )

        task = AgentTask(
            project_id=proj_row.id,
            chapter_id=None,
            task_type="comment_cleanup",
            status="pending",
            priority=10,  # 最低优, 空闲时跑
            # P0 修复: comment_cleanup 是评论系统内部任务, 不应在用户任务页
            # 出现刷屏。 用户能看但前端默认隐藏 / 后端默认不返。
            visibility="internal",
            domain="review",
            task_kind="comment_cleanup",
            payload={
                "retention_days": retention_days,
                "enqueue_source": source,
            },
        )
        db.add(task)
        await db.flush()
        logger.info(
            "queue: enqueue comment_cleanup retention=%s source=%s task_id=%s",
            retention_days, source, task.id,
        )
        return EnqueueResult(task_id=task.id)


_queue_singleton: ReviewQueueService | None = None


def get_review_queue() -> ReviewQueueService:
    global _queue_singleton
    if _queue_singleton is None:
        _queue_singleton = ReviewQueueService()
    return _queue_singleton


__all__ = [
    "EnqueueResult",
    "ReviewQueueService",
    "get_review_queue",
    "ENQUEUE_SOURCE_AUTO_PIPELINE",
    "ENQUEUE_SOURCE_AUTO_COMMENT",
    "ENQUEUE_SOURCE_WORKER_START",
    "ENQUEUE_SOURCE_MANUAL_API",
]
