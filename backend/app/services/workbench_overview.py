from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta
from typing import Iterable

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.comment_review import ReviewComment, ReviewCommentGroup
from app.models.model_call_event import ModelCallEvent
from app.models.model_provider import ModelProvider
from app.models.project import Chapter, Project
from app.models.deepstudy import StudyRun, WritingTechnique
from app.models.study import StudyMaterial
from app.models.task import AgentTask
from app.schemas.workbench import (
    DomainKey,
    WorkbenchAction,
    WorkbenchDomainCard,
    WorkbenchMetric,
    WorkbenchModelSummary,
    WorkbenchOverviewRead,
    WorkbenchPrimaryTask,
    WorkbenchRecentOutput,
    WorkbenchRisk,
    WorkbenchScope,
    WorkbenchWorkerSummary,
)

DOMAIN_TITLES: dict[DomainKey, str] = {
    "writing": "创作",
    "study": "研读",
    "feedback": "反馈",
    "memory": "知识",
    "governance": "治理",
}

DOMAIN_ROUTES: dict[DomainKey, str] = {
    "writing": "/workbench/writing",
    "study": "/workbench/study",
    "feedback": "/workbench/feedback",
    "memory": "/workbench/memory",
    "governance": "/workbench/governance",
}


def domain_for_task_type(task_type: str | None) -> DomainKey:
    value = (task_type or "").lower()
    if value in {"chapter_pipeline", "project_bootstrap", "rewrite_from_discussion"}:
        return "writing"
    if value.startswith("study") or value.startswith("deepstudy") or value == "graph_materialise":
        return "study"
    if value.startswith("reader_review") or value.startswith("comment_") or "discussion" in value:
        return "feedback"
    if value.startswith("memory") or value in {"agent_memory", "knowledge_sync"}:
        return "memory"
    return "governance"


class WorkbenchOverviewService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.now = datetime.utcnow()
        self.today_start = self.now.replace(hour=0, minute=0, second=0, microsecond=0)

    async def build(self, project_id: int | None = None, domain: DomainKey | None = None) -> WorkbenchOverviewRead:
        project = await self._get_project(project_id) if project_id else None
        tasks = await self._recent_tasks(project_id, limit=80)
        task_counts = Counter(t.status for t in tasks)
        domain_counts = Counter(domain_for_task_type(t.task_type) for t in tasks)
        risks = await self._risks(project_id, tasks)
        outputs = await self._recent_outputs(project_id)
        worker = self._worker_summary(tasks)
        model_health = await self._model_health(project_id)
        primary = self._primary_task(tasks)
        domains = await self._domains(project_id, tasks, domain_counts, risks)
        actions = self._recommended_actions(project_id, primary, risks, worker)
        top_stats = await self._top_stats(project_id, task_counts, risks, model_health)

        if domain:
            domains = [d for d in domains if d.key == domain]
            risks = [r for r in risks if r.domain == domain]
            actions = [a for a in actions if a.domain == domain]
            outputs = [o for o in outputs if o.domain == domain]

        return WorkbenchOverviewRead(
            scope=WorkbenchScope(
                mode="project" if project_id else "global",
                project_id=project_id,
                project_name=project.name if project else None,
                domain=domain,
            ),
            top_stats=top_stats,
            domains=domains,
            primary_task=primary,
            risks=risks[:12],
            recommended_actions=actions[:10],
            recent_outputs=outputs[:12],
            worker=worker,
            model_health=model_health,
            as_of=self.now,
        )

    async def _get_project(self, project_id: int) -> Project | None:
        return await self.db.get(Project, project_id)

    async def _recent_tasks(self, project_id: int | None, limit: int = 80) -> list[AgentTask]:
        stmt = select(AgentTask)
        if project_id:
            stmt = stmt.where(AgentTask.project_id == project_id)
        stmt = stmt.order_by(desc(AgentTask.updated_at), desc(AgentTask.id)).limit(limit)
        return list((await self.db.execute(stmt)).scalars().all())

    async def _top_stats(
        self,
        project_id: int | None,
        task_counts: Counter,
        risks: list[WorkbenchRisk],
        model_health: WorkbenchModelSummary,
    ) -> list[WorkbenchMetric]:
        chapter_stmt = select(func.count(Chapter.id))
        word_stmt = select(func.coalesce(func.sum(Chapter.actual_word_count), 0))
        if project_id:
            chapter_stmt = chapter_stmt.where(Chapter.project_id == project_id)
            word_stmt = word_stmt.where(Chapter.project_id == project_id)
        chapters = int((await self.db.execute(chapter_stmt)).scalar_one() or 0)
        words = int((await self.db.execute(word_stmt)).scalar_one() or 0)
        return [
            WorkbenchMetric(key="chapters", label="章节", value=chapters, tone="neutral"),
            WorkbenchMetric(key="words", label="成稿字数", value=words, unit="字", tone="ok" if words else "neutral"),
            WorkbenchMetric(key="running_tasks", label="运行任务", value=task_counts.get("running", 0), tone="ok" if task_counts.get("running", 0) else "neutral"),
            WorkbenchMetric(key="failed_tasks", label="失败任务", value=task_counts.get("failed", 0), tone="danger" if task_counts.get("failed", 0) else "neutral"),
            WorkbenchMetric(key="risks", label="风险", value=len(risks), tone="warning" if risks else "ok"),
            WorkbenchMetric(key="cost_today", label="今日成本", value=round(model_health.cost_today_usd, 4), unit="$", tone="neutral"),
        ]

    async def _domains(
        self,
        project_id: int | None,
        tasks: list[AgentTask],
        domain_counts: Counter,
        risks: list[WorkbenchRisk],
    ) -> list[WorkbenchDomainCard]:
        comments_pending = await self._count(ReviewComment, project_id, ReviewComment.status.in_(["new", "grouped", "discussing"]))
        study_runs = await self._count(StudyRun, project_id, StudyRun.status.in_(["queued", "running", "paused"]))
        techniques = await self._count(WritingTechnique, project_id)
        failed_models = await self._recent_model_failures(project_id)
        data = {
            "writing": [
                WorkbenchMetric(key="tasks", label="近期任务", value=domain_counts.get("writing", 0)),
                WorkbenchMetric(key="running", label="运行中", value=sum(1 for t in tasks if domain_for_task_type(t.task_type) == "writing" and t.status == "running")),
            ],
            "study": [
                WorkbenchMetric(key="runs", label="拆书运行", value=study_runs),
                WorkbenchMetric(key="techniques", label="沉淀技巧", value=techniques),
            ],
            "feedback": [
                WorkbenchMetric(key="pending_comments", label="待处理评论", value=comments_pending, tone="warning" if comments_pending else "ok"),
                WorkbenchMetric(key="tasks", label="评审任务", value=domain_counts.get("feedback", 0)),
            ],
            "memory": [
                WorkbenchMetric(key="techniques", label="技巧库", value=techniques),
                WorkbenchMetric(key="tasks", label="知识任务", value=domain_counts.get("memory", 0)),
            ],
            "governance": [
                WorkbenchMetric(key="model_failures", label="模型失败", value=failed_models, tone="danger" if failed_models else "ok"),
                WorkbenchMetric(key="tasks", label="治理任务", value=domain_counts.get("governance", 0)),
            ],
        }
        cards: list[WorkbenchDomainCard] = []
        for key in DOMAIN_TITLES:
            domain_risks = [r for r in risks if r.domain == key]
            running = any(domain_for_task_type(t.task_type) == key and t.status in {"running", "pending"} for t in tasks)
            status = "blocked" if any(r.severity == "critical" for r in domain_risks) else "warning" if domain_risks else "running" if running else "idle"
            cards.append(WorkbenchDomainCard(
                key=key,
                title=DOMAIN_TITLES[key],
                status=status,
                summary=self._domain_summary(key, status, data[key]),
                metrics=data[key],
                risks=domain_risks[:3],
                actions=self._domain_actions(key, project_id)[:3],
                route=DOMAIN_ROUTES[key],
            ))
        return cards

    def _domain_summary(self, key: DomainKey, status: str, metrics: list[WorkbenchMetric]) -> str:
        if status == "blocked":
            return f"{DOMAIN_TITLES[key]}存在阻塞项，需要优先处理。"
        if status == "warning":
            return f"{DOMAIN_TITLES[key]}有待处理风险。"
        if status == "running":
            return f"{DOMAIN_TITLES[key]}正在运行中。"
        metric_text = "，".join(f"{m.label}{m.value}" for m in metrics[:2])
        return metric_text or f"{DOMAIN_TITLES[key]}暂无活跃任务。"

    async def _risks(self, project_id: int | None, tasks: list[AgentTask]) -> list[WorkbenchRisk]:
        risks: list[WorkbenchRisk] = []
        for task in tasks:
            if task.status != "failed":
                continue
            domain = domain_for_task_type(task.task_type)
            risks.append(WorkbenchRisk(
                key=f"task:{task.id}:failed",
                domain=domain,
                severity="critical",
                title=f"任务失败 #{task.id}",
                summary=(task.error or task.task_type or "任务失败")[:240],
                entity_type="task",
                entity_id=task.id,
                project_id=task.project_id,
                chapter_id=task.chapter_id,
                task_id=task.id,
                route=f"/tasks/{task.id}",
                created_at=task.updated_at,
            ))
        stale_cutoff = self.now - timedelta(minutes=30)
        for task in tasks:
            if task.status == "running" and task.updated_at and task.updated_at < stale_cutoff:
                risks.append(WorkbenchRisk(
                    key=f"task:{task.id}:stale",
                    domain=domain_for_task_type(task.task_type),
                    severity="warning",
                    title=f"任务长时间运行 #{task.id}",
                    summary="任务超过 30 分钟未更新，建议检查 Worker 或查看步骤日志。",
                    entity_type="task",
                    entity_id=task.id,
                    project_id=task.project_id,
                    chapter_id=task.chapter_id,
                    task_id=task.id,
                    route=f"/tasks/{task.id}",
                    created_at=task.updated_at,
                ))
        blocking_groups = await self._review_group_risks(project_id)
        risks.extend(blocking_groups)
        model_failures = await self._recent_model_failure_rows(project_id, limit=5)
        for row in model_failures:
            risks.append(WorkbenchRisk(
                key=f"model:{row.id}:failed",
                domain="governance",
                severity="warning" if row.level != "critical" else "critical",
                title="模型调用失败",
                summary=(row.summary or row.failure_message or row.failure_type or row.model_name or "模型调用失败")[:240],
                entity_type="model_call",
                entity_id=row.id,
                project_id=row.project_id,
                chapter_id=row.chapter_id,
                task_id=row.task_id,
                route="/model-observability",
                created_at=row.created_at,
            ))
        return sorted(risks, key=lambda r: (0 if r.severity == "critical" else 1, r.created_at or datetime.min), reverse=False)

    async def _review_group_risks(self, project_id: int | None) -> list[WorkbenchRisk]:
        stmt = select(ReviewCommentGroup).where(ReviewCommentGroup.status.in_(["new", "discussing", "rewrite_queued"]))
        if project_id:
            stmt = stmt.where(ReviewCommentGroup.project_id == project_id)
        stmt = stmt.order_by(desc(ReviewCommentGroup.updated_at)).limit(8)
        groups = list((await self.db.execute(stmt)).scalars().all())
        risks: list[WorkbenchRisk] = []
        for group in groups:
            severity = "critical" if group.severity in {"high", "blocker"} else "warning"
            risks.append(WorkbenchRisk(
                key=f"review_group:{group.id}",
                domain="feedback",
                severity=severity,
                title=group.title or f"反馈问题包 #{group.id}",
                summary=(group.summary or group.status or "反馈问题待处理")[:240],
                entity_type="review_group",
                entity_id=group.id,
                project_id=group.project_id,
                chapter_id=group.chapter_id,
                route="/reviews",
                created_at=group.updated_at,
            ))
        return risks

    async def _recent_outputs(self, project_id: int | None) -> list[WorkbenchRecentOutput]:
        outputs: list[WorkbenchRecentOutput] = []
        chapter_stmt = select(Chapter).order_by(desc(Chapter.updated_at)).limit(5)
        if project_id:
            chapter_stmt = chapter_stmt.where(Chapter.project_id == project_id)
        chapters = list((await self.db.execute(chapter_stmt)).scalars().all())
        for chapter in chapters:
            outputs.append(WorkbenchRecentOutput(
                key=f"chapter:{chapter.id}",
                domain="writing",
                title=f"第 {chapter.chapter_no} 章 · {chapter.title}",
                summary=chapter.status,
                entity_type="chapter",
                entity_id=chapter.id,
                project_id=chapter.project_id,
                chapter_id=chapter.id,
                route=f"/projects/{chapter.project_id}/chapters/{chapter.id}",
                created_at=chapter.updated_at,
            ))
        material_stmt = select(StudyMaterial).order_by(desc(StudyMaterial.updated_at)).limit(4)
        if project_id:
            material_stmt = material_stmt.where(StudyMaterial.project_id == project_id)
        materials = list((await self.db.execute(material_stmt)).scalars().all())
        for material in materials:
            outputs.append(WorkbenchRecentOutput(
                key=f"study_material:{material.id}",
                domain="study",
                title=material.title,
                summary=material.study_status,
                entity_type="study_material",
                entity_id=material.id,
                project_id=material.project_id,
                route="/study/library",
                created_at=material.updated_at,
            ))
        return sorted(outputs, key=lambda o: o.created_at or datetime.min, reverse=True)

    def _primary_task(self, tasks: list[AgentTask]) -> WorkbenchPrimaryTask | None:
        if not tasks:
            return None
        task = sorted(tasks, key=lambda t: self._task_priority(t), reverse=True)[0]
        domain = domain_for_task_type(task.task_type)
        return WorkbenchPrimaryTask(
            id=task.id,
            domain=domain,
            title=self._task_title(task),
            task_type=task.task_type,
            task_kind=task.task_type,
            status=task.status,
            project_id=task.project_id,
            chapter_id=task.chapter_id,
            progress_current=1 if task.status in {"running", "succeeded", "failed"} else 0,
            progress_total=1,
            progress_percent=100 if task.status in {"succeeded", "failed"} else 50 if task.status == "running" else 0,
            current_step=task.status,
            error=task.error,
            route=f"/tasks/{task.id}",
            started_at=task.started_at,
        )

    def _task_priority(self, task: AgentTask) -> int:
        status = {"running": 100000, "pending": 90000, "failed": 80000, "succeeded": 30000}.get(task.status, 0)
        return status + task.id

    def _task_title(self, task: AgentTask) -> str:
        if task.task_type == "chapter_pipeline" and task.chapter_id:
            return f"写作流水线 · 章节 #{task.chapter_id}"
        if task.task_type == "project_bootstrap":
            return "项目启动任务"
        return task.task_type or f"任务 #{task.id}"

    def _worker_summary(self, tasks: list[AgentTask]) -> WorkbenchWorkerSummary:
        running = [t for t in tasks if t.status == "running"]
        pending = [t for t in tasks if t.status == "pending"]
        failed = [t for t in tasks if t.status == "failed"]
        stale_cutoff = self.now - timedelta(minutes=30)
        stale = [t for t in running if t.updated_at and t.updated_at < stale_cutoff]
        return WorkbenchWorkerSummary(
            state="running" if running else "pending" if pending else "idle",
            loop_state="task_running" if running else None,
            current_task_id=running[0].id if running else None,
            running_count=len(running),
            pending_count=len(pending),
            failed_count=len(failed),
            stale_running_tasks=len(stale),
            last_heartbeat_at=max((t.updated_at for t in tasks if t.updated_at), default=None),
        )

    async def _model_health(self, project_id: int | None) -> WorkbenchModelSummary:
        providers = list((await self.db.execute(select(ModelProvider))).scalars().all())
        recent_failures = await self._recent_model_failures(project_id)
        slow_stmt = select(func.count(ModelCallEvent.id)).where(
            ModelCallEvent.created_at >= self.today_start,
            ModelCallEvent.latency_ms.is_not(None),
            ModelCallEvent.latency_ms >= 30000,
        )
        cost_stmt = select(func.coalesce(func.sum(ModelCallEvent.cost_usd), 0.0)).where(ModelCallEvent.created_at >= self.today_start)
        if project_id:
            slow_stmt = slow_stmt.where(ModelCallEvent.project_id == project_id)
            cost_stmt = cost_stmt.where(ModelCallEvent.project_id == project_id)
        slow_calls = int((await self.db.execute(slow_stmt)).scalar_one() or 0)
        cost_today = float((await self.db.execute(cost_stmt)).scalar_one() or 0.0)
        healthy = sum(1 for p in providers if getattr(p, "is_active", True))
        return WorkbenchModelSummary(
            providers_total=len(providers),
            providers_healthy=healthy,
            providers_degraded=0,
            providers_failed=max(0, len(providers) - healthy),
            recent_failures=recent_failures,
            slow_calls=slow_calls,
            cost_today_usd=round(cost_today, 6),
        )

    async def _recent_model_failures(self, project_id: int | None) -> int:
        stmt = select(func.count(ModelCallEvent.id)).where(
            ModelCallEvent.created_at >= self.today_start,
            ModelCallEvent.status.in_(["failed", "fallback_failed"]),
        )
        if project_id:
            stmt = stmt.where(ModelCallEvent.project_id == project_id)
        return int((await self.db.execute(stmt)).scalar_one() or 0)

    async def _recent_model_failure_rows(self, project_id: int | None, limit: int) -> list[ModelCallEvent]:
        stmt = select(ModelCallEvent).where(
            ModelCallEvent.created_at >= self.today_start,
            ModelCallEvent.status.in_(["failed", "fallback_failed"]),
        )
        if project_id:
            stmt = stmt.where(ModelCallEvent.project_id == project_id)
        stmt = stmt.order_by(desc(ModelCallEvent.created_at)).limit(limit)
        return list((await self.db.execute(stmt)).scalars().all())

    async def _count(self, model, project_id: int | None, *conditions) -> int:
        stmt = select(func.count(model.id))
        if project_id and hasattr(model, "project_id"):
            stmt = stmt.where(model.project_id == project_id)
        for condition in conditions:
            stmt = stmt.where(condition)
        return int((await self.db.execute(stmt)).scalar_one() or 0)

    def _recommended_actions(
        self,
        project_id: int | None,
        primary: WorkbenchPrimaryTask | None,
        risks: list[WorkbenchRisk],
        worker: WorkbenchWorkerSummary,
    ) -> list[WorkbenchAction]:
        actions: list[WorkbenchAction] = []
        if primary and primary.status == "failed" and primary.id:
            actions.append(WorkbenchAction(
                key=f"retry_task:{primary.id}",
                label="重试当前失败任务",
                domain=primary.domain or "governance",
                severity="warning",
                requires_confirm=True,
                description="重新执行当前失败任务。",
                method="POST",
                endpoint=f"/api/tasks/{primary.id}/retry",
                route=f"/tasks/{primary.id}",
            ))
        if worker.running_count == 0:
            actions.append(WorkbenchAction(
                key="open_worker",
                label="打开 Worker 面板",
                domain="governance",
                severity="normal",
                description="查看 Worker 是否需要启动或恢复。",
                route="/worker",
            ))
        if project_id:
            actions.append(WorkbenchAction(
                key="open_project",
                label="进入项目书内",
                domain="writing",
                severity="primary",
                route=f"/projects/{project_id}",
            ))
        if risks:
            actions.append(WorkbenchAction(
                key="open_risks",
                label="处理风险队列",
                domain=risks[0].domain,
                severity="warning",
                route=risks[0].route,
            ))
        return actions

    def _domain_actions(self, domain: DomainKey, project_id: int | None) -> list[WorkbenchAction]:
        routes: dict[DomainKey, tuple[str, str]] = {
            "writing": ("进入创作", f"/projects/{project_id}" if project_id else "/projects"),
            "study": ("打开拆书", "/study/library"),
            "feedback": ("查看反馈", "/reviews"),
            "memory": ("打开知识库", "/memory"),
            "governance": ("治理配置", "/models"),
        }
        label, route = routes[domain]
        return [WorkbenchAction(key=f"open:{domain}", label=label, domain=domain, route=route)]
