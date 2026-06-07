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
import logging
from datetime import datetime, timezone
from typing import Any, Literal

from sqlalchemy import select, func
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

WorkerDomain = Literal["writing", "deepstudy", "discussion", "memory", "model", "all"]


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

        # B3: per-domain in-memory status tracking
        self.domain_statuses: dict[WorkerDomain, DomainWorkerStatus] = {
            "writing": DomainWorkerStatus("writing"),
            "deepstudy": DomainWorkerStatus("deepstudy"),
            "discussion": DomainWorkerStatus("discussion"),
            "memory": DomainWorkerStatus("memory"),
            "model": DomainWorkerStatus("model"),
            "all": DomainWorkerStatus("all"),
        }

        # B3: domain-specific concurrency limits (configurable)
        self.domain_concurrency: dict[WorkerDomain, int] = {
            "writing": 2,      # Allow 2 concurrent writing tasks
            "deepstudy": 1,    # 1 deepstudy at a time (heavy)
            "discussion": 3,   # Discussions are lightweight
            "memory": 1,       # 1 consolidation at a time
            "model": 2,        # 2 health checks concurrently
        }

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
            # P9: 启动讨论 worker 和回收 worker 作为后台任务
            self._discussion_task = asyncio.create_task(
                self._discussion_worker_loop(), name="novelforge-discussion-worker"
            )
            self._recycle_task = asyncio.create_task(
                self._recycle_worker_loop(), name="novelforge-recycle-worker"
            )
            # P10: 启动记忆整理 worker 作为后台任务
            self._memory_consolidation_task = asyncio.create_task(
                self._memory_consolidation_worker_loop(), name="novelforge-memory-consolidation"
            )
            # P3-Model-Failover: 启动 Provider 健康检查 worker
            self._provider_health_task = asyncio.create_task(
                self._provider_health_worker_loop(), name="novelforge-provider-health"
            )
            # P0-DeepStudy: 启动 DeepStudy worker
            self._deepstudy_task = asyncio.create_task(
                self._deepstudy_worker_loop(), name="novelforge-deepstudy"
            )
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
        finally:
            # cancel background tasks
            for t in [getattr(self, '_discussion_task', None), getattr(self, '_recycle_task', None), getattr(self, '_provider_health_task', None), getattr(self, '_deepstudy_task', None), getattr(self, '_memory_consolidation_task', None)]:
                if t and not t.done():
                    t.cancel()

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

            domain_counts: dict[str, int] = {"writing": 0, "deepstudy": 0, "discussion": 0, "memory": 0, "model": 0}
            for t in running_tasks:
                d = t.domain if hasattr(t, 'domain') and t.domain else "writing"
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
                if domain_counts.get(t.domain or "writing", 0)
                < self.domain_concurrency.get(t.domain or "writing", 1)  # type: ignore[arg-type]
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
            ws.current_task_id = task_row.id
            project_id = task_row.project_id
            await db.flush()

        # B3: track domain status when picking a task
        task_domain: WorkerDomain = task_row.domain if hasattr(task_row, 'domain') and task_row.domain else "writing"  # type: ignore[assignment]
        self.domain_statuses[task_domain].current_task_id = task_row.id
        self.domain_statuses[task_domain].last_active_at = datetime.now(timezone.utc)
        self.domain_statuses[task_domain].running = True
        self.domain_statuses["all"].current_task_id = task_row.id

        # P6 §5.2: dispatch by task_type. chapter_pipeline 走老路径
        # (重 timeout / cancel / auto_continue), 其它 4 种走对应 service.
        if task_row.task_type == "chapter_pipeline":
            return await self._run_chapter_pipeline(task_row, ws, policy)
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
                task.cost_usd = result.total_cost_usd
                ws2.current_task_id = None
                await db.flush()
        except Exception as exc:
            err_text = str(exc)
            await self._mark_task_failed(target_task_id, err_text)

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
        worker_domain_status["memory_worker"]["status"] = (
            "running" if self.domain_statuses["memory"].running else "idle"
        )
        worker_domain_status["memory_worker"]["current_job"] = self.domain_statuses["memory"].current_task_id
        worker_domain_status["memory_worker"]["tasks_processed"] = self.domain_statuses["memory"].tasks_processed
        worker_domain_status["model_router"]["tasks_processed"] = self.domain_statuses["model"].tasks_processed

    def _domain_from_task(self, task_row: AgentTask) -> WorkerDomain:
        """Resolve the domain for a task row."""
        domain_val: str = task_row.domain if hasattr(task_row, 'domain') and task_row.domain else "writing"
        # Validate that it's a known WorkerDomain; fall back to "writing"
        if domain_val not in {"writing", "deepstudy", "discussion", "memory", "model", "all"}:
            domain_val = "writing"
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
