"""WorkerController: in-process loop driving the chapter pipeline."""
from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import session_scope
from app.core.errors import bad_request
from app.core.events import Event, event_bus
from app.models.project import Chapter
from app.models.task import AgentTask, WorkerPolicy, WorkerStatus
from app.workers.pipeline import ChapterPipeline


def _today() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d")


class WorkerController:
    """Single-instance async controller.

    State transitions: idle -> running -> paused/stopped. The loop polls the
    `agent_tasks` table for queued chapter tasks and runs them via
    ChapterPipeline.
    """

    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._pause_event = asyncio.Event()
        self._pause_event.set()
        self._stop = asyncio.Event()
        self._lock = asyncio.Lock()

    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def start(self) -> None:
        async with self._lock:
            if self.is_running:
                return
            self._stop.clear()
            self._pause_event.set()
            self._task = asyncio.create_task(self._run_forever(), name="novelforge-worker")
        await event_bus.publish(Event(event_type="worker.started", payload={}))

    async def pause(self) -> None:
        self._pause_event.clear()
        await self._set_state("paused")
        await event_bus.publish(Event(event_type="worker.paused", payload={}))

    async def resume(self) -> None:
        self._pause_event.set()
        await self._set_state("running")
        await event_bus.publish(Event(event_type="worker.resumed", payload={}))

    async def stop(self) -> None:
        self._stop.set()
        self._pause_event.set()  # unblock
        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=10)
            except asyncio.TimeoutError:
                self._task.cancel()
        self._task = None
        await self._set_state("stopped")
        await event_bus.publish(Event(event_type="worker.stopped", payload={}))

    async def status(self) -> dict[str, Any]:
        async with session_scope() as db:
            ws = await self._get_or_create_status(db)
            return {
                "state": ws.state,
                "current_task_id": ws.current_task_id,
                "last_heartbeat_at": ws.last_heartbeat_at.isoformat() if ws.last_heartbeat_at else None,
                "consecutive_failures": ws.consecutive_failures,
                "today_words": ws.today_words,
                "today_cost_usd": ws.today_cost_usd,
                "last_error": ws.last_error,
                "is_loop_alive": self.is_running,
            }

    async def _run_forever(self) -> None:
        try:
            await self._set_state("running")
            while not self._stop.is_set():
                await self._pause_event.wait()
                if self._stop.is_set():
                    break
                did_work = await self._tick()
                if not did_work:
                    # idle: short sleep
                    try:
                        await asyncio.wait_for(self._stop.wait(), timeout=1.0)
                    except asyncio.TimeoutError:
                        pass
        except Exception as exc:  # pragma: no cover
            await self._set_state("error", error=str(exc))

    async def _tick(self) -> bool:
        async with session_scope() as db:
            # reset daily counters at date boundary
            ws = await self._get_or_create_status(db)
            today = _today()
            if ws.last_reset_date != today:
                ws.today_words = 0
                ws.today_cost_usd = 0.0
                ws.last_reset_date = today

            # budget check
            policy = await self._active_policy(db)
            if (
                policy
                and ws.today_cost_usd >= policy.daily_budget_usd
                and policy.daily_budget_usd > 0
            ):
                # pause until tomorrow
                await self._set_state_in_session(db, "paused_budget")
                return False

            # pick next queued task
            task_row = (
                await db.execute(
                    select(AgentTask)
                    .where(AgentTask.status == "pending", AgentTask.task_type == "chapter_pipeline")
                    .order_by(AgentTask.priority.desc(), AgentTask.id.asc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            if task_row is None:
                await self._heartbeat(db, ws)
                return False

            task_row.status = "running"
            task_row.started_at = datetime.utcnow()
            ws.current_task_id = task_row.id
            chapter_id = task_row.chapter_id
            project_id = task_row.project_id
            await db.flush()
            chapter = await db.get(Chapter, chapter_id) if chapter_id else None
            if chapter is None:
                task_row.status = "failed"
                task_row.error = "Chapter missing"
                await self._set_state_in_session(db, "error", error="Chapter missing")
                return False

        # Run the pipeline with a fresh session so commits roll forward per agent.
        pipeline = ChapterPipeline()
        target_task_id = task_row.id
        project_id = task_row.project_id
        chapter_id = task_row.chapter_id
        # Hard upper bound on total pipeline wall time. Per-agent LLM
        # calls already have a 600s read timeout × 2 retries, so a
        # well-behaved run finishes in <10 min. Anything beyond 30 min
        # almost certainly means a stuck connection to the LLM provider;
        # abort the task instead of holding the worker hostage.
        PIPELINE_TIMEOUT_S = 1800
        try:
            async with session_scope() as db:
                task = await db.get(AgentTask, target_task_id)
                chapter = await db.get(Chapter, chapter_id)
                policy = await self._active_policy(db, project_id)
                if policy is None:
                    policy = await self._ensure_default_policy(db, project_id)
                result = await asyncio.wait_for(
                    pipeline.run(db, task=task, chapter=chapter, policy=policy),
                    timeout=PIPELINE_TIMEOUT_S,
                )
                # bump daily counters
                ws2 = await self._get_or_create_status(db)
                ws2.today_words += len(result.final_text)
                ws2.today_cost_usd = round(ws2.today_cost_usd + result.total_cost_usd, 4)
                ws2.consecutive_failures = 0
                task.status = "succeeded"
                task.finished_at = datetime.utcnow()
                task.cost_usd = result.total_cost_usd
                task.input_tokens = result.total_input_tokens
                task.output_tokens = result.total_output_tokens
                ws2.current_task_id = None
                await db.flush()
        except Exception as exc:
            async with session_scope() as db:
                t = await db.get(AgentTask, target_task_id)
                t.status = "failed"
                t.error = str(exc)
                t.finished_at = datetime.utcnow()
                ws3 = await self._get_or_create_status(db)
                ws3.consecutive_failures += 1
                ws3.last_error = str(exc)
                ws3.current_task_id = None
                policy2 = await self._active_policy(db, project_id)
                if (
                    policy2
                    and ws3.consecutive_failures >= policy2.consecutive_fail_stop
                ):
                    await self._set_state_in_session(db, "error", error="consecutive_fail_stop reached")
                    self._stop.set()
            await event_bus.publish(
                Event(event_type="task.failed", payload={"task_id": target_task_id, "error": str(exc)})
            )
        return True

    # ----- helpers -----

    async def _get_or_create_status(self, db: AsyncSession) -> WorkerStatus:
        ws = await db.get(WorkerStatus, 1)
        if ws is None:
            ws = WorkerStatus(id=1, state="idle")
            db.add(ws)
            await db.flush()
        return ws

    async def _set_state_in_session(
        self, db: AsyncSession, state: str, *, error: str | None = None
    ) -> None:
        ws = await self._get_or_create_status(db)
        ws.state = state
        ws.last_heartbeat_at = datetime.utcnow()
        if error is not None:
            ws.last_error = error

    async def _set_state(self, state: str, *, error: str | None = None) -> None:
        async with session_scope() as db:
            await self._set_state_in_session(db, state, error=error)

    async def _heartbeat(self, db: AsyncSession, ws: WorkerStatus) -> None:
        ws.last_heartbeat_at = datetime.utcnow()

    async def _active_policy(
        self, db: AsyncSession, project_id: int | None = None
    ) -> WorkerPolicy | None:
        if project_id is None:
            return None
        return (
            await db.execute(
                select(WorkerPolicy).where(WorkerPolicy.project_id == project_id)
            )
        ).scalar_one_or_none()

    async def _ensure_default_policy(
        self, db: AsyncSession, project_id: int
    ) -> WorkerPolicy:
        pol = await self._active_policy(db, project_id)
        if pol is None:
            pol = WorkerPolicy(project_id=project_id)
            db.add(pol)
            await db.flush()
        return pol


_worker_singleton: WorkerController | None = None


def get_worker() -> WorkerController:
    global _worker_singleton
    if _worker_singleton is None:
        _worker_singleton = WorkerController()
    return _worker_singleton
