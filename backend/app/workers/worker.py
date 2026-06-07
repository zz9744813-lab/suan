"""WorkerController: in-process loop driving the chapter pipeline + P6 event tasks.

P4 改造: 不再只跑 chapter_pipeline, 改成多任务 dispatcher (P6 spec §5):
  - chapter_pipeline    — 章节流水线 (老逻辑, 抽成 _run_chapter_pipeline)
  - reader_review       — 5 读者 Agent 评审一章 (ReaderReviewService)
  - comment_triage      — 主 Agent 评论分流 (CommentTriageService)
  - comment_discussion  — 跑 DiscussionSession participant + synthesis (CommentDiscussionRunner)
  - comment_cleanup     — 7 天过期 review_comments 清理 (CommentCleanupService)

支持: AgentTask.task_type.in_(SUPPORTED_TASKS) (P6 §5.1)
派发: _dispatch_task(task) 按 task_type 分发到 _run_*_task (P6 §5.2)

事件自动触发:
  - chapter_pipeline 成功后, 入队 reader_review (P6 §5.3, 走 ReviewSettings.auto_reader_review)
  - POST /api/reviews/comments 成功后, 入队 comment_triage (P6 §5.4, 走 ReviewSettings.auto_chief_triage)
  - worker 启动时, 入队一次 comment_cleanup (P6 §5.5)
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from sqlalchemy import or_, select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import session_scope
from app.core.errors import bad_request
from app.core.events import Event, event_bus
from app.models.project import Chapter
from app.models.task import AgentTask, WorkerPolicy, WorkerStatus
from app.workers.pipeline import ChapterPipeline

logger = logging.getLogger(__name__)

# ================================================================
# B3: Worker horizontal scaling — domain partitioning
# ================================================================

WorkerDomain = Literal["writing", "deepstudy", "discussion", "review", "memory", "model", "all"]


class DomainWorkerStatus:
    """Per-domain (horizontal partition) worker status.

    Tracks the current task, processed count, error count, and
    uptime for a single domain partition (e.g. "writing",
    "deepstudy").  This is an in-memory structure, NOT a DB model.
    (The DB model ``WorkerStatus`` lives in ``app.models.task``.)
    """

    def __init__(self, domain: WorkerDomain) -> None:
        self.domain: WorkerDomain = domain
        self.running: bool = False
        self.current_task_id: int | None = None
        self.current_run_id: int | None = None
        self.tasks_processed: int = 0
        self.errors_count: int = 0
        self.last_active_at: datetime | None = None
        self.uptime_started_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "domain": self.domain,
            "running": self.running,
            "current_task_id": self.current_task_id,
            "current_run_id": self.current_run_id,
            "tasks_processed": self.tasks_processed,
            "errors_count": self.errors_count,
            "last_active_at": self.last_active_at.isoformat() if self.last_active_at else None,
            "uptime_seconds": (datetime.now(timezone.utc) - self.uptime_started_at).total_seconds() if self.uptime_started_at else 0,
        }


# Global registry for domain status (written by WorkerController,
# read by the /multi-status API endpoint in routers/worker.py).
worker_domain_status: dict[str, dict[str, Any]] = {
    "writing_worker": {"status": "idle", "current_task": None, "tasks_processed": 0},
    "deepstudy_worker": {"status": "idle", "current_run": None, "tasks_processed": 0},
    "discussion_worker": {"status": "idle", "current_thread": None, "tasks_processed": 0},
    "review_worker": {"status": "idle", "current_task": None, "tasks_processed": 0},
    "memory_worker": {"status": "idle", "current_job": None, "tasks_processed": 0},
    "model_router": {"status": "healthy", "providers_up": 0, "providers_total": 0, "tasks_processed": 0},
}


def _today() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d")


# P6 §5.1 — 5 种 worker 支持的任务类型. AgentTask.task_type 命中
# 其中之一才会被 worker 拉起. 其它 (e.g. 旧的 study / graph /
# memory / learning) 不在本轮 P0-P5 范围, 走老路径或手工触发.
SUPPORTED_TASKS: frozenset[str] = frozenset({
    "chapter_pipeline",     # P0-P3 老逻辑, 章节流水线
    "reader_review",        # P2, ReaderReviewService — 5 读者评审
    "comment_triage",       # P3, CommentTriageService — 主 Agent 分流
    "comment_discussion",   # P3 + P4, CommentDiscussionRunner — 跑讨论室
    "comment_cleanup",      # P4, CommentCleanupService — 7 天过期清理
    "rewrite_from_discussion",  # P9, Chief 结论触发的修改任务
    "project_bootstrap",    # 双模式: 全自动启动项目 (LLM 生成大纲/人物/设定)
})


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
        self.worker_id = f"worker-{uuid.uuid4().hex[:10]}"
        self.lease_seconds = 3600
        self.crash_count = 0
        self.last_crash_at: datetime | None = None

        # B3: per-domain in-memory status tracking
        self.domain_statuses: dict[WorkerDomain, DomainWorkerStatus] = {
            "writing": DomainWorkerStatus("writing"),
            "deepstudy": DomainWorkerStatus("deepstudy"),
            "discussion": DomainWorkerStatus("discussion"),
            "review": DomainWorkerStatus("review"),
            "memory": DomainWorkerStatus("memory"),
            "model": DomainWorkerStatus("model"),
            "all": DomainWorkerStatus("all"),
        }

        # B3: domain-specific concurrency limits (configurable)
        self.domain_concurrency: dict[WorkerDomain, int] = {
            "writing": 2,      # Allow 2 concurrent writing tasks
            "deepstudy": 1,    # 1 deepstudy at a time (heavy)
            "discussion": 3,   # Discussions are lightweight
            "review": 2,       # Reader/comment tasks are isolated from writing
            "memory": 1,       # 1 consolidation at a time
            "model": 2,        # 2 health checks concurrently
        }

    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    def _on_loop_done(self, task: asyncio.Task) -> None:
        if self._stop.is_set():
            return
        exc = None
        try:
            exc = task.exception()
        except asyncio.CancelledError:
            return
        asyncio.create_task(self._mark_loop_crashed(exc))

    def _spawn_background_loop(self, coro: Any, domain: WorkerDomain, name: str) -> asyncio.Task:
        task = asyncio.create_task(coro, name=name)
        task.add_done_callback(lambda done: self._on_background_loop_done(done, domain, name))
        return task

    def _on_background_loop_done(self, task: asyncio.Task, domain: WorkerDomain, name: str) -> None:
        if self._stop.is_set():
            return
        exc: BaseException | None = None
        try:
            exc = task.exception()
        except asyncio.CancelledError:
            return
        if exc is None:
            return
        self.domain_statuses[domain].errors_count += 1
        logger.exception("Background worker loop %s crashed: %s", name, exc)
        asyncio.create_task(event_bus.publish(Event(
            event_type="worker.background_loop_crashed",
            payload={"worker_id": self.worker_id, "domain": domain, "loop": name, "error": str(exc)},
        )))

    async def _mark_loop_crashed(self, exc: BaseException | None) -> None:
        self.crash_count += 1
        self.last_crash_at = datetime.utcnow()
        message = str(exc) if exc else "worker loop exited unexpectedly"
        await self._set_state("error", error=message)
        await event_bus.publish(Event(
            event_type="worker.loop_crashed",
            payload={
                "worker_id": self.worker_id,
                "error": message,
                "crash_count": self.crash_count,
            },
        ))

    async def recover_stale_tasks(
        self,
        *,
        reason: str = "manual",
        stale_after_seconds: int | None = None,
    ) -> dict[str, int]:
        """Recover tasks that were marked running but have no live lease."""
        now = datetime.utcnow()
        cutoff = now - timedelta(seconds=stale_after_seconds or self.lease_seconds)
        recovered = 0
        failed = 0
        inspected = 0
        async with session_scope() as db:
            rows = (await db.execute(
                select(AgentTask).where(
                    AgentTask.status == "running",
                    AgentTask.task_type.in_(SUPPORTED_TASKS),
                    or_(
                        AgentTask.lease_owner != self.worker_id,
                        AgentTask.lease_expires_at < now,
                        AgentTask.lease_expires_at.is_(None),
                        AgentTask.last_heartbeat_at < cutoff,
                        AgentTask.last_heartbeat_at.is_(None),
                    ),
                )
            )).scalars().all()
            for task in rows:
                inspected += 1
                task.lease_owner = None
                task.lease_expires_at = None
                task.last_heartbeat_at = None
                task.error = (task.error or "")[:1500]
                note = f"Recovered stale running task ({reason})"
                task.error = f"{task.error}\n{note}".strip()
                task.retry_count = int(task.retry_count or 0) + 1
                if task.retry_count >= int(task.max_retries or 3):
                    task.status = "failed"
                    task.finished_at = now
                    failed += 1
                else:
                    task.status = "pending"
                    task.started_at = None
                    task.finished_at = None
                    task.not_before_at = now
                    recovered += 1
            ws = await self._get_or_create_status(db)
            if rows and ws.current_task_id in {task.id for task in rows}:
                ws.current_task_id = None
            if rows:
                ws.last_heartbeat_at = now
        if inspected:
            await event_bus.publish(Event(
                event_type="worker.stale_tasks_recovered",
                payload={
                    "reason": reason,
                    "inspected": inspected,
                    "recovered": recovered,
                    "failed": failed,
                },
            ))
        return {"inspected": inspected, "recovered": recovered, "failed": failed}

    async def start(self) -> None:
        async with self._lock:
            if self.is_running:
                return
            self._stop.clear()
            self._pause_event.set()
            self._task = asyncio.create_task(self._run_forever(), name="novelforge-worker")
            self._task.add_done_callback(self._on_loop_done)
        await self.recover_stale_tasks(reason="worker_start")
        # R12.1 / P0-WORKER-1 fix: clear stale failure state from a
        # previous run before the new loop starts. Otherwise the UI
        # keeps showing "consecutive_failures=N", "current_task_id=X"
        # and the last error from a run that may have happened hours
        # (or days) ago, even though the user just clicked 启动 on a
        # fresh process. See worker log around 2026-06-03 00:48 for
        # the historical failure that prompted this fix.
        await self._clear_stale_failure_state()
        # P6 §5.5: 入队一次 comment_cleanup (worker 启动时, 跑空闲时)
        # 已有 pending 任务时由 ReviewQueueService 跳过.
        try:
            from app.services.review import (
                ENQUEUE_SOURCE_WORKER_START,
                get_review_queue,
            )
            async with session_scope() as db:
                # 默认 7 天 retention, 跟 P6 §1.3 强制一致
                from app.models.comment_review import ReviewSettings
                # 找项目的 retention_days 中位值, fallback 7
                retention = 7
                settings_rows = (await db.execute(
                    select(ReviewSettings)
                )).scalars().all()
                if settings_rows:
                    retention = max(s.retention_days for s in settings_rows)
                await get_review_queue().enqueue_comment_cleanup(
                    db, retention_days=retention,
                    source=ENQUEUE_SOURCE_WORKER_START,
                )
        except Exception as exc:  # 不让 cleanup 入队失败阻挡 worker 启动
            await event_bus.publish(Event(
                event_type="worker.startup_warning",
                payload={"warning": "comment_cleanup enqueue failed", "error": str(exc)},
            ))
        await event_bus.publish(Event(event_type="worker.started", payload={}))

    async def _clear_stale_failure_state(self) -> None:
        """Reset WorkerStatus fields that track the PREVIOUS run.

        Only runs on start(), never on resume() — pause/resume are
        mid-run state transitions and we don't want to wipe evidence
        of an in-flight problem.
        """
        async with session_scope() as db:
            ws = await self._get_or_create_status(db)
            ws.consecutive_failures = 0
            ws.current_task_id = None
            ws.last_error = None
            ws.state = "running"
            ws.last_heartbeat_at = datetime.utcnow()

    async def pause(self) -> None:
        self._pause_event.clear()
        await self._set_state("paused")
        await event_bus.publish(Event(event_type="worker.paused", payload={}))

    async def resume(self) -> None:
        self._pause_event.set()
        await self._set_state("running")
        await event_bus.publish(Event(event_type="worker.resumed", payload={}))

    async def stop(self) -> None:
        import logging as _logging, traceback as _tb
        _logging.getLogger(__name__).warning("Worker stop() called\n%s", ''.join(_tb.format_stack()))
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
            now = datetime.utcnow()
            cutoff = now - timedelta(seconds=self.lease_seconds)
            stale_running_tasks = (await db.execute(
                select(func.count(AgentTask.id)).where(
                    AgentTask.status == "running",
                    AgentTask.task_type.in_(SUPPORTED_TASKS),
                    or_(
                        AgentTask.lease_owner != self.worker_id,
                        AgentTask.lease_expires_at < now,
                        AgentTask.lease_expires_at.is_(None),
                        AgentTask.last_heartbeat_at < cutoff,
                        AgentTask.last_heartbeat_at.is_(None),
                    ),
                )
            )).scalar() or 0
            return {
                "state": ws.state,
                "loop_state": "alive" if self.is_running else "dead",
                "worker_id": self.worker_id,
                "current_task_id": ws.current_task_id,
                "last_heartbeat_at": ws.last_heartbeat_at.isoformat() if ws.last_heartbeat_at else None,
                "consecutive_failures": ws.consecutive_failures,
                "today_words": ws.today_words,
                "today_cost_usd": ws.today_cost_usd,
                "last_error": ws.last_error,
                "is_loop_alive": self.is_running,
                "last_crash_at": self.last_crash_at.isoformat() if self.last_crash_at else None,
                "crash_count": self.crash_count,
                "stale_running_tasks": stale_running_tasks,
                "domain_statuses": {
                    key: value.to_dict() for key, value in self.domain_statuses.items()
                },
            }

    async def _run_forever(self) -> None:
        import logging as _logging
        _log = _logging.getLogger(__name__)
        try:
            await self._set_state("running")
            # P9: 启动讨论 worker 和回收 worker 作为后台任务
            self._discussion_task = self._spawn_background_loop(
                self._discussion_worker_loop(), "discussion", "novelforge-discussion-worker"
            )
            self._recycle_task = self._spawn_background_loop(
                self._recycle_worker_loop(), "discussion", "novelforge-recycle-worker"
            )
            # P10: 启动记忆整理 worker 作为后台任务
            self._memory_consolidation_task = self._spawn_background_loop(
                self._memory_consolidation_worker_loop(), "memory", "novelforge-memory-consolidation"
            )
            # P3-Model-Failover: 启动 Provider 健康检查 worker
            self._provider_health_task = self._spawn_background_loop(
                self._provider_health_worker_loop(), "model", "novelforge-provider-health"
            )
            # P0-DeepStudy: 启动 DeepStudy worker
            self._deepstudy_task = self._spawn_background_loop(
                self._deepstudy_worker_loop(), "deepstudy", "novelforge-deepstudy"
            )
            while not self._stop.is_set():
                await self._pause_event.wait()
                if self._stop.is_set():
                    _log.warning("Worker _run_forever: _stop set after pause_event.wait()")
                    break
                did_work = await self._tick()
                self._ensure_background_loops_alive()
                if not did_work:
                    # idle: short sleep
                    try:
                        await asyncio.wait_for(self._stop.wait(), timeout=1.0)
                    except asyncio.TimeoutError:
                        pass
            _log.warning("Worker _run_forever: loop exited normally (stop=%s)", self._stop.is_set())
        except Exception as exc:  # pragma: no cover
            import logging
            logging.getLogger(__name__).exception("Worker _run_forever crashed: %s", exc)
            await self._set_state("error", error=str(exc))
            # 关键修复: 崩溃时回滚当前 running 任务, 防止永久卡在 running
            try:
                await self.recover_stale_tasks(reason="worker_crash")
            except Exception as recover_exc:
                logging.getLogger(__name__).warning("Failed to recover stale tasks after crash: %s", recover_exc)
        finally:
            # cancel background tasks
            for t in [getattr(self, '_discussion_task', None), getattr(self, '_recycle_task', None), getattr(self, '_provider_health_task', None), getattr(self, '_deepstudy_task', None), getattr(self, '_memory_consolidation_task', None)]:
                if t and not t.done():
                    t.cancel()

    def _ensure_background_loops_alive(self) -> None:
        if self._stop.is_set():
            return
        specs = [
            ("_discussion_task", "discussion", "novelforge-discussion-worker", self._discussion_worker_loop),
            ("_recycle_task", "discussion", "novelforge-recycle-worker", self._recycle_worker_loop),
            ("_memory_consolidation_task", "memory", "novelforge-memory-consolidation", self._memory_consolidation_worker_loop),
            ("_provider_health_task", "model", "novelforge-provider-health", self._provider_health_worker_loop),
            ("_deepstudy_task", "deepstudy", "novelforge-deepstudy", self._deepstudy_worker_loop),
        ]
        for attr, domain, name, factory in specs:
            current = getattr(self, attr, None)
            if current is None or current.done():
                setattr(self, attr, self._spawn_background_loop(factory(), domain, name))

    async def _discussion_worker_loop(self) -> None:
        """P9: 每 20 秒轮询 pending_discussion 线程。"""
        while not self._stop.is_set():
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=20.0)
                return  # stop was set
            except asyncio.TimeoutError:
                pass
            if not self._pause_event.is_set():
                continue
            try:
                self.domain_statuses["discussion"].running = True
                self.domain_statuses["discussion"].last_active_at = datetime.now(timezone.utc)
                from app.workers.discussion_worker import discussion_worker_tick
                await discussion_worker_tick()
            except Exception as exc:
                self.domain_statuses["discussion"].errors_count += 1
                import logging
                logging.getLogger(__name__).warning(f"Discussion worker tick error: {exc}")
            finally:
                self.domain_statuses["discussion"].running = False
                self._sync_domain_to_global()

    async def _recycle_worker_loop(self) -> None:
        """P9: 每 60 秒扫描到期讨论线程。"""
        while not self._stop.is_set():
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=60.0)
                return  # stop was set
            except asyncio.TimeoutError:
                pass
            if not self._pause_event.is_set():
                continue
            try:
                from app.workers.discussion_recycle_worker import discussion_recycle_tick
                await discussion_recycle_tick()
            except Exception as exc:
                import logging
                logging.getLogger(__name__).warning(f"Recycle worker tick error: {exc}")

    async def _memory_consolidation_worker_loop(self) -> None:
        """P10: 每 60 秒运行记忆整理 (过期清理)."""
        while not self._stop.is_set():
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=60.0)
                return  # stop was set
            except asyncio.TimeoutError:
                pass
            if not self._pause_event.is_set():
                continue
            try:
                self.domain_statuses["memory"].running = True
                self.domain_statuses["memory"].last_active_at = datetime.now(timezone.utc)
                from app.services.agent_memory_service import MemoryConsolidatorService
                async with session_scope() as db:
                    svc = MemoryConsolidatorService()
                    await svc.expire_temporary_memories(db)
                    await db.commit()
            except Exception as exc:
                self.domain_statuses["memory"].errors_count += 1
                logger.warning(f"Memory consolidation tick error: {exc}")
            finally:
                self.domain_statuses["memory"].running = False
                self._sync_domain_to_global()

    async def _provider_health_worker_loop(self) -> None:
        """P3-Model-Failover: 每 300 秒轻量健康检查 + half_open 恢复."""
        while not self._stop.is_set():
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=300.0)
                return  # stop was set
            except asyncio.TimeoutError:
                pass
            if not self._pause_event.is_set():
                continue
            try:
                self.domain_statuses["model"].running = True
                self.domain_statuses["model"].last_active_at = datetime.now(timezone.utc)
                from app.services.provider_health import ProviderHealthService
                from app.services.model_circuit_breaker import CircuitBreakerService
                from app.models.model_provider import ModelProvider
                async with session_scope() as db:
                    await ProviderHealthService().check_all_enabled(db, lightweight=True)
                    # 检查 half_open 恢复
                    await CircuitBreakerService().check_half_open(db)
                    # B3: update model_router global status provider counts
                    providers_up = await db.execute(
                        select(func.count(ModelProvider.id)).where(
                            ModelProvider.enabled.is_(True),
                            ModelProvider.circuit_state == "closed",
                        )
                    )
                    up = providers_up.scalar() or 0
                    providers_total = await db.execute(
                        select(func.count(ModelProvider.id))
                    )
                    total = providers_total.scalar() or 0
                    worker_domain_status["model_router"]["providers_up"] = up
                    worker_domain_status["model_router"]["providers_total"] = total
                    worker_domain_status["model_router"]["status"] = "healthy" if up > 0 else "degraded"
            except Exception as exc:
                self.domain_statuses["model"].errors_count += 1
                logger.warning(f"Provider health tick error: {exc}")
            finally:
                self.domain_statuses["model"].running = False
                self._sync_domain_to_global()

    async def _deepstudy_worker_loop(self) -> None:
        """P0-DeepStudy: 每 10 秒轮询 queued/running StudyRun 并推进 DAG。"""
        while not self._stop.is_set():
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=10.0)
                return  # stop was set
            except asyncio.TimeoutError:
                pass
            if not self._pause_event.is_set():
                continue
            try:
                self.domain_statuses["deepstudy"].running = True
                self.domain_statuses["deepstudy"].last_active_at = datetime.now(timezone.utc)
                from app.workers.deepstudy_worker import deepstudy_tick
                await deepstudy_tick()
            except Exception as exc:
                self.domain_statuses["deepstudy"].errors_count += 1
                import logging
                logging.getLogger(__name__).warning(f"DeepStudy worker tick error: {exc}")
            finally:
                self.domain_statuses["deepstudy"].running = False
                self._sync_domain_to_global()

    async def _tick(self) -> bool:
        # P6 §5.1: pick 5 种支持任务类型中的下一个 pending
        async with session_scope() as db:
            # reset daily counters at date boundary
            ws = await self._get_or_create_status(db)
            today = _today()
            if ws.last_reset_date != today:
                ws.today_words = 0
                ws.today_cost_usd = 0.0
                ws.last_reset_date = today

            # B3: domain-specific concurrency limits.
            # Count running tasks by domain so we don't pick a task
            # from a domain that is already at capacity.
            running_tasks = (
                await db.execute(
                    select(AgentTask).where(
                        AgentTask.status == "running",
                        AgentTask.task_type.in_(SUPPORTED_TASKS),
                    )
                )
            ).scalars().all()

            domain_counts: dict[str, int] = {"writing": 0, "deepstudy": 0, "discussion": 0, "review": 0, "memory": 0, "model": 0}
            for t in running_tasks:
                d = self._domain_from_task(t)
                domain_counts[d] = domain_counts.get(d, 0) + 1

            # P1-2 fix: pick the next task FIRST, then load its
            # project's policy. Previously the worker called
            # ``_active_policy(db)`` with ``project_id=None`` which
            # always returned None, so the budget / word-goal checks
            # were never enforced. Now we resolve policy against the
            # task's own project_id.
            # P6 §5.1: 改用 SUPPORTED_TASKS in_(...) 派发
            # BUG-3 fix: 排除尚未到重试时间的任务 (not_before_at > now)
            # B3: pick up to 10 pending tasks, then filter by domain concurrency
            _now = datetime.utcnow()
            pending_tasks = (
                await db.execute(
                    select(AgentTask)
                    .where(
                        AgentTask.status == "pending",
                        AgentTask.task_type.in_(SUPPORTED_TASKS),
                        (AgentTask.not_before_at == None) | (AgentTask.not_before_at <= _now),  # noqa: E711
                    )
                    .order_by(AgentTask.priority.desc(), AgentTask.id.asc())
                    .limit(10)
                )
            ).scalars().all()

            # B3: only pick tasks from domains that are under the concurrency limit
            eligible_tasks = [
                t for t in pending_tasks
                if domain_counts.get(self._domain_from_task(t), 0)
                < self.domain_concurrency.get(self._domain_from_task(t), 1)
            ]
            task_row = eligible_tasks[0] if eligible_tasks else None
            if task_row is None:
                await self._heartbeat(db, ws)
                return False

            # resolve the project policy now that we know the task
            policy = await self._active_policy(db, task_row.project_id)
            if policy is None:
                policy = await self._ensure_default_policy(db, task_row.project_id)

            # budget check (now correctly scoped to the task's project)
            if (
                policy.daily_budget_usd > 0
                and ws.today_cost_usd >= policy.daily_budget_usd
            ):
                # pause until tomorrow
                await self._set_state_in_session(db, "paused_budget")
                return False
            if (
                policy.daily_word_goal > 0
                and ws.today_words >= policy.daily_word_goal
            ):
                await self._set_state_in_session(db, "paused_goal")
                return False

            task_row.status = "running"
            task_row.started_at = datetime.utcnow()
            task_row.last_heartbeat_at = task_row.started_at
            task_row.lease_owner = self.worker_id
            task_row.lease_expires_at = task_row.started_at + timedelta(seconds=self.lease_seconds)
            task_row.correlation_id = task_row.correlation_id or f"task-{task_row.id}-{uuid.uuid4().hex[:8]}"
            ws.current_task_id = task_row.id
            project_id = task_row.project_id
            await db.flush()

        # B3: track domain status when picking a task
        task_domain = self._domain_from_task(task_row)
        self.domain_statuses[task_domain].current_task_id = task_row.id
        self.domain_statuses[task_domain].last_active_at = datetime.now(timezone.utc)
        self.domain_statuses[task_domain].running = True
        self.domain_statuses["all"].current_task_id = task_row.id

        # P6 §5.2: dispatch by task_type. chapter_pipeline 走老路径
        # (重 timeout / cancel / auto_continue), 其它走对应 service.
        if task_row.task_type == "chapter_pipeline":
            return await self._run_chapter_pipeline(task_row, ws, policy)
        if task_row.task_type == "project_bootstrap":
            return await self._run_project_bootstrap(task_row, ws, policy)
        return await self._dispatch_event_task(task_row, ws, policy)

    # ----- P6 §5.2: 派发 (event task) -----

    async def _dispatch_event_task(
        self,
        task_row: AgentTask,
        ws: WorkerStatus,
        policy: WorkerPolicy,
    ) -> bool:
        """P6 §5.2: 4 种非 chapter_pipeline 任务的派发入口.

        跟 chapter_pipeline 不同:
          - 不重 30min timeout (这 4 种 task 都很快, 5min 封顶)
          - 不在 budget 失败时停 worker (event task 跟 budget 解耦)
          - 失败时把 task 标 failed, 发 task.failed 事件
        """
        target_task_id = task_row.id
        task_domain = self._domain_from_task(task_row)
        # event task 跟 project 的 daily_budget / daily_word_goal 解耦
        # (P6 §4 任务不等同 chapter pipeline 的产出, 不算 word).
        try:
            if task_row.task_type == "reader_review":
                await self._run_reader_review(task_row, ws)
            elif task_row.task_type == "comment_triage":
                await self._run_comment_triage(task_row, ws)
            elif task_row.task_type == "comment_discussion":
                await self._run_comment_discussion(task_row, ws)
            elif task_row.task_type == "comment_cleanup":
                await self._run_comment_cleanup(task_row, ws)
            elif task_row.task_type == "rewrite_from_discussion":
                await self._run_rewrite_from_discussion(task_row, ws)
            else:
                # 不应发生, _pick 已经过滤 SUPPORTED_TASKS
                raise RuntimeError(
                    f"_dispatch_event_task: 不支持 task_type={task_row.task_type}"
                )
            self._clear_domain_task(task_domain)
            return True
        except Exception as exc:
            err_text = str(exc)
            async with session_scope() as db:
                t = await db.get(AgentTask, target_task_id)
                t.status = "failed"
                t.error = err_text
                t.finished_at = datetime.utcnow()
                ws3 = await self._get_or_create_status(db)
                ws3.consecutive_failures += 0  # event 失败不算 worker 失败
                ws3.last_error = err_text
                ws3.current_task_id = None
            await event_bus.publish(
                Event(event_type="task.failed", payload={
                    "task_id": target_task_id,
                    "error": err_text,
                    "task_type": task_row.task_type,
                })
            )
            self._clear_domain_task(task_domain)
            return False

    async def _run_reader_review(
        self,
        task_row: AgentTask,
        ws: WorkerStatus,
    ) -> None:
        """P6 §5.2: 5 读者 Agent 评审一章. 调 ReaderReviewService."""
        from app.services.review import get_reader_review_service
        payload = task_row.payload or {}
        trigger = payload.get("trigger", "chapter_completed")
        target_task_id = task_row.id
        async with session_scope() as db:
            t = await db.get(AgentTask, target_task_id)
            outcome = await get_reader_review_service().run_for_chapter(
                db,
                project_id=task_row.project_id,
                chapter_id=task_row.chapter_id,
                trigger=trigger,
            )
            t.status = "succeeded"
            t.lease_owner = None
            t.lease_expires_at = None
            t.last_heartbeat_at = None
            t.finished_at = datetime.utcnow()
            t.cost_usd = outcome.total_cost_usd
            t.input_tokens = outcome.total_input_tokens
            t.output_tokens = outcome.total_output_tokens
            t.payload = {
                **payload,
                "run_id": outcome.run_id,
                "status": outcome.status,
                "comment_ids": outcome.comment_ids,
                "succeeded_readers": outcome.reader_keys_succeeded,
                "failed_readers": outcome.reader_keys_failed,
            }
            await self._set_state_in_session(db, "running")
            ws2 = await self._get_or_create_status(db)
            ws2.current_task_id = None
            await db.flush()
        await event_bus.publish(Event(
            event_type="reader_review.completed",
            payload={
                "task_id": target_task_id,
                "project_id": task_row.project_id,
                "chapter_id": task_row.chapter_id,
                "run_id": outcome.run_id,
                "status": outcome.status,
                "comment_count": len(outcome.comment_ids),
            },
        ))

    async def _run_comment_triage(
        self,
        task_row: AgentTask,
        ws: WorkerStatus,
    ) -> None:
        """P6 §5.2 + §5.4: 主 Agent 评论分流. 调 CommentTriageService."""
        from app.services.review import get_comment_triage_service
        target_task_id = task_row.id
        async with session_scope() as db:
            t = await db.get(AgentTask, target_task_id)
            outcome = await get_comment_triage_service().run_for_chapter(
                db,
                project_id=task_row.project_id,
                chapter_id=task_row.chapter_id,
            )
            t.status = "succeeded"
            t.finished_at = datetime.utcnow()
            t.payload = {
                **(task_row.payload or {}),
                "new_comment_count": outcome.new_comment_count,
                "reply_count": outcome.reply_count,
                "group_count": outcome.group_count,
                "discuss_count": outcome.discuss_count,
                "ignore_count": outcome.ignore_count,
            }
            await self._set_state_in_session(db, "running")
            ws2 = await self._get_or_create_status(db)
            ws2.current_task_id = None
            await db.flush()
        await event_bus.publish(Event(
            event_type="comment_triage.completed",
            payload={
                "task_id": target_task_id,
                "project_id": task_row.project_id,
                "chapter_id": task_row.chapter_id,
                "new_comment_count": outcome.new_comment_count,
                "discuss_count": outcome.discuss_count,
            },
        ))

    async def _run_comment_discussion(
        self,
        task_row: AgentTask,
        ws: WorkerStatus,
    ) -> None:
        """P6 §5.2 + §4.4: 跑 DiscussionSession participant + synthesis.

        P3 discussion_bridge 已经写好 session + meta turn + task 入队,
        P4 worker 接管剩下 participant + synthesis 跑.
        """
        from app.services.review import get_comment_discussion_runner
        target_task_id = task_row.id
        async with session_scope() as db:
            t = await db.get(AgentTask, target_task_id)
            outcome = await get_comment_discussion_runner().run_for_task(db, task=t)
            if outcome.session_status == "failed":
                t.status = "failed"
                t.error = outcome.error or "comment_discussion failed"
            else:
                t.status = "succeeded"
            t.finished_at = datetime.utcnow()
            t.payload = {
                **(task_row.payload or {}),
                "session_id": outcome.session_id,
                "group_id": outcome.group_id,
                "turn_count": outcome.turn_count,
                "session_status": outcome.session_status,
            }
            await self._set_state_in_session(db, "running")
            ws2 = await self._get_or_create_status(db)
            ws2.current_task_id = None
            await db.flush()
        await event_bus.publish(Event(
            event_type="comment_discussion.completed",
            payload={
                "task_id": target_task_id,
                "session_id": outcome.session_id,
                "group_id": outcome.group_id,
                "turn_count": outcome.turn_count,
                "session_status": outcome.session_status,
            },
        ))

    async def _run_comment_cleanup(
        self,
        task_row: AgentTask,
        ws: WorkerStatus,
    ) -> None:
        """P6 §5.2 + §4.6 + §5.5: 清理 7 天前过期的 review_comments."""
        from app.services.review import get_comment_cleanup_service
        target_task_id = task_row.id
        payload = task_row.payload or {}
        retention = int(payload.get("retention_days", 7))
        async with session_scope() as db:
            t = await db.get(AgentTask, target_task_id)
            outcome = await get_comment_cleanup_service().cleanup_expired(
                db, retention_days=retention,
            )
            t.status = "succeeded" if not outcome.error else "failed"
            t.finished_at = datetime.utcnow()
            t.error = outcome.error
            t.payload = {
                **payload,
                "scanned": outcome.scanned,
                "deleted": outcome.deleted,
                "skipped_immortal": outcome.skipped_immortal,
                "skipped_discussing": outcome.skipped_discussing,
                "retention_days": outcome.retention_days,
            }
            await self._set_state_in_session(db, "running")
            ws2 = await self._get_or_create_status(db)
            ws2.current_task_id = None
            await db.flush()
        await event_bus.publish(Event(
            event_type="comment_cleanup.completed",
            payload={
                "task_id": target_task_id,
                "deleted": outcome.deleted,
                "scanned": outcome.scanned,
                "retention_days": outcome.retention_days,
            },
        ))

    async def _run_rewrite_from_discussion(
        self,
        task_row: AgentTask,
        ws: WorkerStatus,
    ) -> None:
        """P9: 讨论结论触发的 rewrite 任务。复用 chapter_pipeline 逻辑。"""
        chapter_id = task_row.chapter_id
        target_task_id = task_row.id
        if chapter_id is None:
            await self._mark_task_failed(target_task_id, "Chapter missing for rewrite_from_discussion")
            return

        pipeline = ChapterPipeline()
        try:
            async with session_scope() as db:
                task = await db.get(AgentTask, target_task_id)
                chapter = await db.get(Chapter, chapter_id)
                if chapter is None:
                    await self._mark_task_failed(target_task_id, "Chapter missing")
                    return
                policy = await self._active_policy(db, task_row.project_id)
                if policy is None:
                    policy = await self._ensure_default_policy(db, task_row.project_id)
                # Inject discussion instruction into task if present
                payload = task_row.payload or {}
                instruction = payload.get("rewrite_instruction", "")
                # P0 返工 Phase 5.1 修复: 原版只取 instruction 但没传给
                # pipeline.run (签名不接受), 改写指令直接丢失。这里把
                # instruction 写回 task.payload["rewrite_instruction"] 让
                # pipeline 内部读取拼到 drafter prompt。
                if instruction and not payload.get("rewrite_instruction"):
                    payload["rewrite_instruction"] = instruction
                    task.payload = payload
                result = await asyncio.wait_for(
                    pipeline.run(db, task=task, chapter=chapter, policy=policy),
                    timeout=1800,
                )
                ws2 = await self._get_or_create_status(db)
                ws2.today_words += len(result.final_text)
                ws2.today_cost_usd = round(ws2.today_cost_usd + result.total_cost_usd, 4)
                ws2.consecutive_failures = 0
                task.status = "succeeded"
                task.finished_at = datetime.utcnow()
                task.lease_owner = None
                task.lease_expires_at = None
                task.last_heartbeat_at = None
                task.cost_usd = result.total_cost_usd
                ws2.current_task_id = None
                await db.flush()
        except Exception as exc:
            err_text = str(exc)
            await self._mark_task_failed(target_task_id, err_text)

    # ----- 双模式: project_bootstrap (全自动启动) -----

    async def _run_project_bootstrap_v2(self, task_id: int) -> bool:
        from app.models.memory import MemoryCharacter
        from app.models.project import Bible, Chapter, Outline, Project
        from app.services.llm.client import LLMClient, LLMMessage
        from app.services.llm.router import LLMRouter

        router = LLMRouter(LLMClient())
        try:
            async with session_scope() as db:
                task = await db.get(AgentTask, task_id)
                if task is None:
                    return False
                project = await db.get(Project, task.project_id)
                if project is None:
                    await self._mark_task_failed(task_id, f"Project {task.project_id} not found")
                    return False
                task.status = "running"
                task.started_at = task.started_at or datetime.utcnow()
                task.last_heartbeat_at = datetime.utcnow()

                outline_prompt = (
                    "请为长篇小说生成前 30 章大纲。只输出 JSON："
                    '{"outlines":[{"chapter_no":1,"title":"标题","summary":"50-100字简介","importance":80}]}。\n'
                    f"书名：{project.name}\n类型：{project.genre}\n简介：{project.description or '无'}"
                )
                _, outline_result = await router.chat(
                    db, "Planner", [LLMMessage(role="user", content=outline_prompt)],
                    max_tokens=4000, response_format={"type": "json_object"},
                    stream=False, project_id=project.id, task_id=task.id,
                    task_type="project_bootstrap",
                    step_key="bootstrap_outline",
                )
                outline_data = self._parse_bootstrap_json(outline_result.content)
                outline_items = outline_data.get("outlines") or outline_data.get("items") or []
                if not isinstance(outline_items, list):
                    outline_items = []

                existing_outlines = (await db.execute(
                    select(Outline).where(Outline.project_id == project.id)
                )).scalars().all()
                existing_outline_nos = {row.chapter_no for row in existing_outlines}
                outlines_created: list[Outline] = []
                for item in outline_items[:30]:
                    if not isinstance(item, dict):
                        continue
                    chapter_no = int(item.get("chapter_no") or len(existing_outline_nos) + len(outlines_created) + 1)
                    if chapter_no in existing_outline_nos:
                        continue
                    outline = Outline(
                        project_id=project.id,
                        chapter_no=chapter_no,
                        title=str(item.get("title") or f"第 {chapter_no} 章"),
                        summary=item.get("summary"),
                        importance=int(item.get("importance") or 50),
                        target_word_count=int(item.get("target_word_count") or 3000),
                    )
                    db.add(outline)
                    outlines_created.append(outline)
                    existing_outline_nos.add(chapter_no)
                await db.flush()

                outline_context = "\n".join(
                    f"{o.chapter_no}. {o.title}: {o.summary or ''}"
                    for o in (existing_outlines + outlines_created)[:12]
                )
                character_prompt = (
                    "请为这本小说设计主要角色。只输出 JSON："
                    '{"characters":[{"name":"姓名","role":"protagonist|antagonist|supporting",'
                    '"profile":{"description":"人物简介"}}]}。\n'
                    f"书名：{project.name}\n类型：{project.genre}\n大纲：\n{outline_context}"
                )
                _, character_result = await router.chat(
                    db, "Planner", [LLMMessage(role="user", content=character_prompt)],
                    max_tokens=2500, response_format={"type": "json_object"},
                    stream=False, project_id=project.id, task_id=task.id,
                    task_type="project_bootstrap",
                    step_key="bootstrap_characters",
                )
                character_data = self._parse_bootstrap_json(character_result.content)
                character_items = character_data.get("characters") or character_data.get("items") or []
                if not isinstance(character_items, list):
                    character_items = []
                existing_chars = (await db.execute(
                    select(MemoryCharacter).where(MemoryCharacter.project_id == project.id)
                )).scalars().all()
                existing_char_names = {c.name for c in existing_chars}
                chars_created = 0
                for item in character_items[:15]:
                    if not isinstance(item, dict):
                        continue
                    name = str(item.get("name") or "").strip()
                    if not name or name in existing_char_names:
                        continue
                    db.add(MemoryCharacter(
                        project_id=project.id,
                        name=name,
                        role=item.get("role") or "supporting",
                        tags=item.get("tags") or [],
                        base_profile=item.get("profile") if isinstance(item.get("profile"), dict) else {},
                    ))
                    existing_char_names.add(name)
                    chars_created += 1
                await db.flush()

                bible_prompt = (
                    "请为这本小说生成世界观与主线设定。只输出 JSON："
                    '{"world":"世界观","main_plot":"主线","rules":["规则1"],"protagonist":"主角设定"}。\n'
                    f"书名：{project.name}\n类型：{project.genre}\n大纲：\n{outline_context}"
                )
                _, bible_result = await router.chat(
                    db, "Planner", [LLMMessage(role="user", content=bible_prompt)],
                    max_tokens=1800, response_format={"type": "json_object"},
                    stream=False, project_id=project.id, task_id=task.id,
                    task_type="project_bootstrap",
                    step_key="bootstrap_bible",
                )
                bible_data = self._parse_bootstrap_json(bible_result.content)
                bible = (await db.execute(
                    select(Bible).where(Bible.project_id == project.id, Bible.is_active.is_(True))
                )).scalar_one_or_none()
                if bible is None:
                    bible = Bible(project_id=project.id, title="主设定", content={})
                    db.add(bible)
                    await db.flush()
                bible.content = {
                    **(bible.content or {}),
                    **{k: v for k, v in bible_data.items() if v not in (None, "")},
                }
                bible.version += 1

                first_outline = (await db.execute(
                    select(Outline)
                    .where(Outline.project_id == project.id)
                    .order_by(Outline.chapter_no.asc(), Outline.id.asc())
                    .limit(1)
                )).scalar_one_or_none()
                first_task_id = None
                if first_outline is not None:
                    chapter = (await db.execute(
                        select(Chapter).where(
                            Chapter.project_id == project.id,
                            Chapter.chapter_no == first_outline.chapter_no,
                        )
                    )).scalar_one_or_none()
                    if chapter is None:
                        chapter = Chapter(
                            project_id=project.id,
                            outline_id=first_outline.id,
                            chapter_no=first_outline.chapter_no,
                            title=first_outline.title,
                            target_word_count=first_outline.target_word_count,
                            status="queued",
                        )
                        db.add(chapter)
                        await db.flush()
                    existing_task = (await db.execute(
                        select(AgentTask).where(
                            AgentTask.project_id == project.id,
                            AgentTask.chapter_id == chapter.id,
                            AgentTask.task_type == "chapter_pipeline",
                            AgentTask.status.in_(["pending", "running"]),
                        )
                    )).scalar_one_or_none()
                    if existing_task is None:
                        pipeline_task = AgentTask(
                            project_id=project.id,
                            chapter_id=chapter.id,
                            task_type="chapter_pipeline",
                            status="pending",
                            priority=100,
                            domain="writing",
                            payload={"mode": "full", "auto_launched": True},
                            display_title=f"写作: 第 {chapter.chapter_no} 章 {chapter.title}",
                        )
                        db.add(pipeline_task)
                        await db.flush()
                        first_task_id = pipeline_task.id
                    else:
                        first_task_id = existing_task.id

                task.status = "succeeded"
                task.finished_at = datetime.utcnow()
                task.lease_owner = None
                task.lease_expires_at = None
                task.last_heartbeat_at = None
                task.cost_usd = (
                    (outline_result.cost_usd or 0)
                    + (character_result.cost_usd or 0)
                    + (bible_result.cost_usd or 0)
                )
                task.input_tokens = (
                    (outline_result.input_tokens or 0)
                    + (character_result.input_tokens or 0)
                    + (bible_result.input_tokens or 0)
                )
                task.output_tokens = (
                    (outline_result.output_tokens or 0)
                    + (character_result.output_tokens or 0)
                    + (bible_result.output_tokens or 0)
                )
                task.summary_json = {
                    "outlines_created": len(outlines_created),
                    "characters_created": chars_created,
                    "bible_updated": True,
                    "first_task_id": first_task_id,
                }
                ws = await self._get_or_create_status(db)
                ws.current_task_id = None
                ws.consecutive_failures = 0
            await event_bus.publish(Event(
                event_type="project_bootstrap.completed",
                payload={"task_id": task_id},
            ))
            return True
        except Exception as exc:
            await self._mark_task_failed(task_id, str(exc)[:2000])
            return False

    @staticmethod
    def _parse_bootstrap_json(text: str) -> dict[str, Any]:
        if not text:
            return {}
        try:
            obj = json.loads(text)
            if isinstance(obj, dict):
                return obj
            if isinstance(obj, list):
                return {"items": obj}
        except Exception:
            pass
        match = re.search(r"(\{[\s\S]*\}|\[[\s\S]*\])", text)
        if not match:
            return {}
        try:
            obj = json.loads(match.group(1))
            if isinstance(obj, dict):
                return obj
            if isinstance(obj, list):
                return {"items": obj}
        except Exception:
            return {}
        return {}

    async def _run_project_bootstrap(
        self,
        task_row: AgentTask,
        ws: WorkerStatus,
        policy: WorkerPolicy,
    ) -> bool:
        """全自动模式: 用 LLM 生成大纲/人物/设定, 然后启动第一章写作。

        流程:
        1. 调用 LLM 生成大纲 (JSON 格式)
        2. 写入 Outline 行
        3. 生成人物/设定 → 写入 MemoryCharacter / Bible
        4. 从第一个大纲创建 Chapter
        5. 入队 chapter_pipeline 任务
        """
        return await self._run_project_bootstrap_v2(task_row.id)

        from app.models.project import Bible, Chapter, Outline, Project
        from app.models.memory import MemoryCharacter
        from app.services.llm.router import LLMRouter
        from app.services.prompt_engine import PromptEngine

        payload = task_row.payload or {}
        project_id = task_row.project_id
        project = await self.db.get(Project, project_id)
        if not project:
            await self._mark_task_failed(task_row.id, f"Project {project_id} not found")
            return False

        task_row.status = "running"
        task_row.started_at = datetime.utcnow()
        await self.db.flush()

        try:
            router = LLMRouter(self.db)
            engine = PromptEngine(self.db)

            # Step 1: 用 LLM 生成大纲
            outline_prompt = (
                f"你是一位专业的长篇小说大纲规划师。\n"
                f"请为小说《{project.name}》生成大纲，类型：{project.genre}。\n"
                f"目标章节数：{project.target_chapter_count}，请生成前 30 章的详细大纲。\n"
                f"{'简介：' + (project.description or '无')}\n\n"
                f"请严格按照以下 JSON 格式输出，不要输出任何其他内容：\n"
                f'```json\n'
                f'[\n'
                f'  {{"chapter_no": 1, "title": "章节标题", "summary": "章节简介(50-100字)", "importance": 80}},\n'
                f'  ...\n'
                f']\n'
                f'```'
            )

            resolved = await router.resolve("PlannerAgent", project.genre or "default")
            messages = [
                {"role": "system", "content": "你是专业的网文大纲规划师，擅长构建长篇小说的故事线。只输出纯JSON，不要任何解释。"},
                {"role": "user", "content": outline_prompt},
            ]
            import json as _json
            from app.services.llm.client import LLMMessage
            llm_messages = [LLMMessage(role=m["role"], content=m["content"]) for m in messages]
            resp = await router.call(resolved, llm_messages, max_tokens=4000, temperature=0.7)

            # 解析大纲 JSON
            raw = resp.content.strip()
            # 尝试提取 JSON 块
            json_match = re.search(r'\[[\s\S]*\]', raw)
            if json_match:
                outline_items = _json.loads(json_match.group())
            else:
                outline_items = _json.loads(raw)

            outlines_created = []
            for item in outline_items[:30]:  # 最多 30 章
                o = Outline(
                    project_id=project_id,
                    chapter_no=int(item.get("chapter_no", len(outlines_created) + 1)),
                    title=str(item.get("title", f"第{len(outlines_created)+1}章")),
                    summary=item.get("summary"),
                    importance=int(item.get("importance", 50)),
                    target_word_count=3000,
                )
                self.db.add(o)
                outlines_created.append(o)
            await self.db.flush()

            # Step 2: 用 LLM 生成人物
            char_prompt = (
                f"你是一位专业的网文人物设计师。\n"
                f"请为小说《{project.name}》({project.genre})设计主要人物。\n"
                f"大纲摘要：\n"
                + "\n".join(f"- 第{o.chapter_no}章: {o.title} - {o.summary or ''}" for o in outlines_created[:10])
                + "\n\n请严格按照以下 JSON 格式输出，不要输出任何其他内容：\n"
                f'```json\n'
                f'[\n'
                f'  {{"name": "人物名", "role": "protagonist|antagonist|supporting", "profile": {{"description": "人物描述"}}}},\n'
                f'  ...\n'
                f']\n'
                f'```'
            )
            char_messages = [
                LLMMessage(role="system", content="你是网文人物设计师，只输出纯JSON。"),
                LLMMessage(role="user", content=char_prompt),
            ]
            resp2 = await router.call(resolved, char_messages, max_tokens=2000, temperature=0.7)
            raw2 = resp2.content.strip()
            json_match2 = re.search(r'\[[\s\S]*\]', raw2)
            if json_match2:
                char_items = _json.loads(json_match2.group())
            else:
                try:
                    char_items = _json.loads(raw2)
                except Exception:
                    char_items = []

            chars_created = 0
            for item in char_items[:15]:  # 最多 15 个人物
                c = MemoryCharacter(
                    project_id=project_id,
                    name=str(item.get("name", "未命名")),
                    role=item.get("role", "supporting"),
                    base_profile=item.get("profile", {}),
                )
                self.db.add(c)
                chars_created += 1
            await self.db.flush()

            # Step 3: 更新 Bible (世界观)
            bible_prompt = (
                f"请为小说《{project.name}》({project.genre})写一段世界观设定(200-500字)。\n"
                f"大纲涉及: {', '.join(o.title for o in outlines_created[:5])}\n"
                f"只输出设定文本，不要其他内容。"
            )
            bible_messages = [
                LLMMessage(role="system", content="你是网文世界观设计师，输出纯文本设定。"),
                LLMMessage(role="user", content=bible_prompt),
            ]
            resp3 = await router.call(resolved, bible_messages, max_tokens=1000, temperature=0.7)

            bible = (
                await self.db.execute(
                    select(Bible).where(Bible.project_id == project_id, Bible.is_active.is_(True))
                )
            ).scalar_one_or_none()
            if bible:
                bible.content = {
                    "world": resp3.content.strip(),
                    "protagonist": bible.content.get("protagonist", "（待设定）"),
                }
                bible.version += 1
            await self.db.flush()

            # Step 4: 从第一个大纲创建章节并启动管线
            if outlines_created:
                first_outline = outlines_created[0]
                chapter = Chapter(
                    project_id=project_id,
                    outline_id=first_outline.id,
                    chapter_no=first_outline.chapter_no,
                    title=first_outline.title,
                    target_word_count=first_outline.target_word_count,
                    status="queued",
                )
                self.db.add(chapter)
                await self.db.flush()

                pipeline_task = AgentTask(
                    project_id=project_id,
                    chapter_id=chapter.id,
                    task_type="chapter_pipeline",
                    status="pending",
                    priority=100,
                    domain="writing",
                    payload={"mode": "full", "auto_launched": True},
                    display_title=f"写作: 第{chapter.chapter_no}章 {chapter.title}",
                )
                self.db.add(pipeline_task)
                await self.db.flush()

            # 标记 bootstrap 任务完成
            task_row.status = "succeeded"
            task_row.finished_at = datetime.utcnow()
            task_row.cost_usd = (resp.cost_usd or 0) + (resp2.cost_usd or 0) + (resp3.cost_usd or 0)
            task_row.input_tokens = (resp.input_tokens or 0) + (resp2.input_tokens or 0) + (resp3.input_tokens or 0)
            task_row.output_tokens = (resp.output_tokens or 0) + (resp2.output_tokens or 0) + (resp3.output_tokens or 0)
            task_row.summary_json = {
                "outlines_created": len(outlines_created),
                "characters_created": chars_created,
                "bible_updated": True,
            }
            await self.db.flush()
            return True

        except Exception as exc:
            task_row.status = "failed"
            task_row.error = str(exc)[:2000]
            task_row.finished_at = datetime.utcnow()
            await self.db.flush()
            return False

    # ----- 老 chapter_pipeline 逻辑 (抽出来) -----

    async def _run_chapter_pipeline(
        self,
        task_row: AgentTask,
        ws: WorkerStatus,
        policy: WorkerPolicy,
    ) -> bool:
        """P0-P3 老章节流水线, 抽自原 _tick() 内联.

        关键不变量:
          - 30 min wall-clock 封顶 (PIPELINE_TIMEOUT_S)
          - 'cancelled by user' 异常: 标 cancelled, 不停 worker
          - 其他失败: 标 failed, 累计 consecutive_failures,
            达到 consecutive_fail_stop 时停 worker
          - 成功: 入队下一章 (auto_continue) + P6 §5.3 入队 reader_review
        """
        chapter_id = task_row.chapter_id
        task_domain = self._domain_from_task(task_row)
        if chapter_id is None:
            # 没 chapter 关联的 pipeline 任务不该存在
            await self._mark_task_failed(task_row.id, "Chapter missing")
            self._clear_domain_task(task_domain)
            return False
        # 单独 session 校验 chapter
        async with session_scope() as db:
            chapter = await db.get(Chapter, chapter_id)
            if chapter is None:
                await self._mark_task_failed(task_row.id, "Chapter missing")
                self._clear_domain_task(task_domain)
                return False
            chapter_no = chapter.chapter_no

        pipeline = ChapterPipeline()
        target_task_id = task_row.id
        project_id = task_row.project_id
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

            # P1-1 fix: on success, enqueue the next chapter task so
            # the worker keeps producing 24/7. We do this in a fresh
            # session so the previous transaction is fully committed
            # and the new task is visible to the next tick.
            if policy.auto_continue:
                from app.services.chapter_queue import ChapterQueueService
                async with session_scope() as db:
                    policy2 = await self._active_policy(db, project_id)
                    if policy2 is None:
                        policy2 = await self._ensure_default_policy(db, project_id)
                    next_task = await ChapterQueueService().enqueue_next_chapter_if_needed(
                        db,
                        project_id=project_id,
                        current_chapter_no=chapter_no,
                        policy=policy2,
                    )
                    if next_task is None:
                        await self._emit_event(
                            "worker.waiting_for_outline",
                            {
                                "project_id": project_id,
                                "next_chapter_no": chapter_no + 1,
                                "message": f"第 {chapter_no} 章已完成，等待第 {chapter_no + 1} 章大纲。",
                            },
                        )
                    else:
                        await self._emit_event(
                            "worker.auto_continue_enqueued",
                            {
                                "project_id": project_id,
                                "next_chapter_no": chapter_no + 1,
                                "task_id": next_task.id,
                            },
                        )

            # P6 §5.3: 章节完成后入队 reader_review (auto_reader_review 开关)
            # 用 fresh session, 跟 P1-1 同样模式.
            try:
                from app.services.review import (
                    ENQUEUE_SOURCE_AUTO_PIPELINE,
                    get_review_queue,
                )
                async with session_scope() as db:
                    await get_review_queue().enqueue_reader_review(
                        db,
                        project_id=project_id,
                        chapter_id=chapter_id,
                        trigger="chapter_completed",
                        source=ENQUEUE_SOURCE_AUTO_PIPELINE,
                    )
            except Exception as exc:  # 入队失败不阻挡主线
                await event_bus.publish(Event(
                    event_type="worker.reader_review_enqueue_failed",
                    payload={
                        "project_id": project_id, "chapter_id": chapter_id,
                        "error": str(exc),
                    },
                ))
        except asyncio.TimeoutError:
            self._clear_domain_task(task_domain)
            async with session_scope() as db:
                t = await db.get(AgentTask, target_task_id)
                t.status = "failed"
                t.error = f"Pipeline exceeded {PIPELINE_TIMEOUT_S}s timeout"
                t.finished_at = datetime.utcnow()
                ws3 = await self._get_or_create_status(db)
                ws3.consecutive_failures += 1
                ws3.last_error = t.error
                ws3.current_task_id = None
            await event_bus.publish(
                Event(event_type="task.failed", payload={"task_id": target_task_id, "error": "pipeline timeout"})
            )
        except Exception as exc:
            err_text = str(exc)
            if "cancelled by user" in err_text:
                async with session_scope() as db:
                    t = await db.get(AgentTask, target_task_id)
                    if t and t.status != "cancelled":
                        t.status = "cancelled"
                        t.finished_at = datetime.utcnow()
                    ws3 = await self._get_or_create_status(db)
                    ws3.current_task_id = None
                await event_bus.publish(
                    Event(event_type="task.cancelled", payload={"task_id": target_task_id})
                )
                self._clear_domain_task(task_domain)
                return False
            async with session_scope() as db:
                t = await db.get(AgentTask, target_task_id)
                t.status = "failed"
                t.error = err_text
                t.finished_at = datetime.utcnow()
                ws3 = await self._get_or_create_status(db)
                ws3.consecutive_failures += 1
                ws3.last_error = err_text
                ws3.current_task_id = None
                policy2 = await self._active_policy(db, project_id)
                if (
                    policy2
                    and ws3.consecutive_failures >= policy2.consecutive_fail_stop
                ):
                    await self._set_state_in_session(db, "error", error="consecutive_fail_stop reached")
                    self._stop.set()
            await event_bus.publish(
                Event(event_type="task.failed", payload={"task_id": target_task_id, "error": err_text})
            )
        self._clear_domain_task(task_domain)
        return True

    async def _mark_task_failed(self, task_id: int, error: str) -> None:
        async with session_scope() as db:
            t = await db.get(AgentTask, task_id)
            if t is None:
                return
            t.retry_count = (t.retry_count or 0) + 1
            t.error = error

            # BUG-3 fix: 当 retry_count < max_retries 时,
            # 将任务重置为 pending 并设置指数退避延迟, 而非直接标 failed.
            # 退避: 2^(retry-1) * 30s = 30s / 60s / 120s / ...
            if t.retry_count < (t.max_retries or 3):
                from datetime import timedelta
                delay_s = min(30 * (2 ** (t.retry_count - 1)), 300)  # 最大 5min
                t.status = "pending"
                t.lease_owner = None
                t.lease_expires_at = None
                t.last_heartbeat_at = None
                t.not_before_at = datetime.utcnow() + timedelta(seconds=delay_s)
                t.started_at = None
                logger.info(
                    "Task %d failed (attempt %d/%d), retry in %ds: %s",
                    task_id, t.retry_count, t.max_retries, delay_s, error[:120],
                )
                ws2 = await self._get_or_create_status(db)
                ws2.current_task_id = None
                # 重试不算作 consecutive_failures
                return

            # 耗尽重试次数, 最终失败
            t.status = "failed"
            t.lease_owner = None
            t.lease_expires_at = None
            t.last_heartbeat_at = None
            t.finished_at = datetime.utcnow()
            ws2 = await self._get_or_create_status(db)
            ws2.consecutive_failures += 1
            ws2.last_error = error
            ws2.current_task_id = None
        await event_bus.publish(Event(
            event_type="task.failed", payload={"task_id": task_id, "error": error},
        ))

    async def _emit_event(self, event_type: str, payload: dict[str, Any]) -> None:
        """Publish a worker-level event (no DB row, just SSE)."""
        await event_bus.publish(Event(event_type=event_type, payload=payload))

    # ----- helpers -----

    def _sync_domain_to_global(self) -> None:
        """Push in-memory domain status to the global registry (read by router)."""
        worker_domain_status["writing_worker"]["status"] = (
            "running" if self.domain_statuses["writing"].running else "idle"
        )
        worker_domain_status["writing_worker"]["current_task"] = self.domain_statuses["writing"].current_task_id
        worker_domain_status["writing_worker"]["tasks_processed"] = self.domain_statuses["writing"].tasks_processed
        worker_domain_status["deepstudy_worker"]["status"] = (
            "running" if self.domain_statuses["deepstudy"].running else "idle"
        )
        worker_domain_status["deepstudy_worker"]["current_run"] = self.domain_statuses["deepstudy"].current_run_id
        worker_domain_status["deepstudy_worker"]["tasks_processed"] = self.domain_statuses["deepstudy"].tasks_processed
        worker_domain_status["discussion_worker"]["status"] = (
            "running" if self.domain_statuses["discussion"].running else "idle"
        )
        worker_domain_status["discussion_worker"]["current_thread"] = self.domain_statuses["discussion"].current_task_id
        worker_domain_status["discussion_worker"]["tasks_processed"] = self.domain_statuses["discussion"].tasks_processed
        worker_domain_status["review_worker"]["status"] = (
            "running" if self.domain_statuses["review"].running else "idle"
        )
        worker_domain_status["review_worker"]["current_task"] = self.domain_statuses["review"].current_task_id
        worker_domain_status["review_worker"]["tasks_processed"] = self.domain_statuses["review"].tasks_processed
        worker_domain_status["memory_worker"]["status"] = (
            "running" if self.domain_statuses["memory"].running else "idle"
        )
        worker_domain_status["memory_worker"]["current_job"] = self.domain_statuses["memory"].current_task_id
        worker_domain_status["memory_worker"]["tasks_processed"] = self.domain_statuses["memory"].tasks_processed
        worker_domain_status["model_router"]["tasks_processed"] = self.domain_statuses["model"].tasks_processed

    def _domain_from_task(self, task_row: AgentTask) -> WorkerDomain:
        """Resolve the domain for a task row."""
        domain_val: str = task_row.domain if hasattr(task_row, 'domain') and task_row.domain else "writing"
        if domain_val not in {"writing", "deepstudy", "discussion", "review", "memory", "model", "all"}:
            return "writing"
        return domain_val  # type: ignore[return-value]

    def _clear_domain_task(self, domain: WorkerDomain) -> None:
        """Clear a domain's current task and mark it idle."""
        ds = self.domain_statuses[domain]
        ds.current_task_id = None
        ds.running = False
        ds.tasks_processed += 1
        self.domain_statuses["all"].current_task_id = None
        self._sync_domain_to_global()

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
