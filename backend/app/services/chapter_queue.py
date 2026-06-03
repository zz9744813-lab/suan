"""ChapterQueueService — auto-continue the next chapter after one finishes.

P1-1 fix: previously the worker only drained existing ``pending``
``chapter_pipeline`` tasks, so as soon as a project ran out of queued
chapters it sat idle. The user had to manually create the next
chapter + task every time, which broke the "24h auto-write" promise.

This service is called by the worker right after a chapter pipeline
finishes successfully. It:

1. Looks up the next chapter number (current + 1) in the same project.
2. If that chapter doesn't exist, tries to materialise it from the
   project's outline (per-outline ``title`` + ``target_word_count``).
3. Skips if there is already a pending/running task for it (avoids
   double-enqueueing when the worker is restarted mid-flight).
4. Otherwise creates a new ``AgentTask(status="pending", task_type=
   "chapter_pipeline")`` so the worker's next tick picks it up.

Honours the project policy's ``auto_continue`` flag — when off, the
service is a no-op so the user can manually drive the queue.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import Chapter, Outline
from app.models.task import AgentTask, WorkerPolicy


class ChapterQueueService:
    """Enqueue the next chapter task for a project, if appropriate."""

    async def enqueue_next_chapter_if_needed(
        self,
        db: AsyncSession,
        *,
        project_id: int,
        current_chapter_no: int,
        policy: WorkerPolicy,
    ) -> AgentTask | None:
        if not policy.auto_continue:
            return None

        next_no = current_chapter_no + 1

        # 1. 查下一章是否已存在
        chapter = (
            await db.execute(
                select(Chapter).where(
                    Chapter.project_id == project_id,
                    Chapter.chapter_no == next_no,
                )
            )
        ).scalar_one_or_none()

        # 2. 不存在则尝试根据 Outline 创建
        if chapter is None:
            outline = (
                await db.execute(
                    select(Outline).where(
                        Outline.project_id == project_id,
                        Outline.chapter_no == next_no,
                    )
                )
            ).scalar_one_or_none()

            if outline is None:
                # Nothing to do. Caller (worker) should surface a
                # "waiting for outline" event so the UI can prompt the
                # user to add more outline entries.
                return None

            chapter = Chapter(
                project_id=project_id,
                outline_id=outline.id,
                chapter_no=outline.chapter_no,
                title=outline.title,
                target_word_count=outline.target_word_count,
                status="queued",
            )
            db.add(chapter)
            await db.flush()

        # 3. 查是否已有 pending/running 任务
        existing_task = (
            await db.execute(
                select(AgentTask).where(
                    AgentTask.project_id == project_id,
                    AgentTask.chapter_id == chapter.id,
                    AgentTask.task_type == "chapter_pipeline",
                    AgentTask.status.in_(["pending", "running"]),
                )
            )
        ).scalar_one_or_none()

        if existing_task is not None:
            return None

        # 4. 创建下一章任务
        task = AgentTask(
            project_id=project_id,
            chapter_id=chapter.id,
            task_type="chapter_pipeline",
            status="pending",
            priority=100,
            payload={
                "auto_continue": True,
                "from_chapter_no": current_chapter_no,
            },
        )
        db.add(task)
        await db.flush()
        return task
