"""Task creation / inspection routes."""
from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.errors import bad_request, not_found
from app.models.project import Chapter
from app.models.task import AgentEvent, AgentStep, AgentTask
from app.schemas import (
    APIResponse,
    AgentEventRead,
    AgentStepRead,
    AgentTaskCreate,
    AgentTaskRead,
    TaskDiagnosisRead,
    TaskDiagnosisStep,
    TaskDiagnosisSuggestion,
    TaskRetryRequest,
)
from app.schemas.task import PIPELINE_STEP_ORDER, STEP_LABELS


router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.get("", response_model=APIResponse[list[AgentTaskRead]])
async def list_tasks(
    project_id: int | None = None,
    chapter_id: int | None = None,
    status: str | None = None,
    visibility: str = "user",
    domain: str | None = None,
    task_kind: str | None = None,
    parent_task_id: int | None = None,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[list[AgentTaskRead]]:
    stmt = select(AgentTask).order_by(AgentTask.id.desc()).limit(min(limit, 200))
    if project_id is not None:
        stmt = stmt.where(AgentTask.project_id == project_id)
    if chapter_id is not None:
        stmt = stmt.where(AgentTask.chapter_id == chapter_id)
    if status is not None:
        stmt = stmt.where(AgentTask.status == status)
    if visibility is not None:
        stmt = stmt.where(AgentTask.visibility == visibility)
    if domain is not None:
        stmt = stmt.where(AgentTask.domain == domain)
    if task_kind is not None:
        stmt = stmt.where(AgentTask.task_kind == task_kind)
    if parent_task_id is not None:
        stmt = stmt.where(AgentTask.parent_task_id == parent_task_id)
    rows = (await db.execute(stmt)).scalars().all()
    return {"ok": True, "data": [AgentTaskRead.model_validate(r) for r in rows]}


@router.post("", response_model=APIResponse[AgentTaskRead])
async def create_task(
    body: AgentTaskCreate, db: AsyncSession = Depends(get_db)
) -> APIResponse[AgentTaskRead]:
    if body.chapter_id is not None:
        ch = await db.get(Chapter, body.chapter_id)
        if ch is None:
            raise not_found("Chapter", body.chapter_id)
    row = AgentTask(
        project_id=body.project_id,
        chapter_id=body.chapter_id,
        task_type=body.task_type,
        priority=body.priority,
        payload=body.payload,
        max_retries=body.max_retries,
    )
    db.add(row)
    await db.flush()
    return {"ok": True, "data": AgentTaskRead.model_validate(row)}


@router.get("/{task_id}", response_model=APIResponse[AgentTaskRead])
async def get_task(task_id: int, db: AsyncSession = Depends(get_db)) -> APIResponse[AgentTaskRead]:
    row = await db.get(AgentTask, task_id)
    if row is None:
        raise not_found("AgentTask", task_id)
    return {"ok": True, "data": AgentTaskRead.model_validate(row)}


@router.get("/{task_id}/steps", response_model=APIResponse[list[AgentStepRead]])
async def task_steps(task_id: int, db: AsyncSession = Depends(get_db)) -> APIResponse[list[AgentStepRead]]:
    rows = (await db.execute(
        select(AgentStep).where(AgentStep.task_id == task_id).order_by(AgentStep.id.asc())
    )).scalars().all()
    return {"ok": True, "data": [AgentStepRead.model_validate(r) for r in rows]}


@router.get("/{task_id}/events", response_model=APIResponse[list[AgentEventRead]])
async def task_events(task_id: int, db: AsyncSession = Depends(get_db)) -> APIResponse[list[AgentEventRead]]:
    rows = (await db.execute(
        select(AgentEvent).where(AgentEvent.task_id == task_id).order_by(AgentEvent.id.asc())
    )).scalars().all()
    return {"ok": True, "data": [AgentEventRead.model_validate(r) for r in rows]}


@router.post("/{task_id}/cancel", response_model=APIResponse[AgentTaskRead])
async def cancel_task(task_id: int, db: AsyncSession = Depends(get_db)) -> APIResponse[AgentTaskRead]:
    row = await db.get(AgentTask, task_id)
    if row is None:
        raise not_found("AgentTask", task_id)
    row.status = "cancelled"
    await db.flush()
    return {"ok": True, "data": AgentTaskRead.model_validate(row)}


@router.post("/{task_id}/retry", response_model=APIResponse[AgentTaskRead])
async def retry_task(
    task_id: int,
    body: TaskRetryRequest | None = None,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[AgentTaskRead]:
    """P1-FUNC-2: configurable retry.

    Modes:
      - ``full`` (default): rerun the whole chapter pipeline from scratch.
      - ``from_failed_step``: rerun starting at ``body.from_step`` (e.g.
        ``"review"``). Previous successful steps are kept on disk and the
        worker rebuilds the in-memory state from the chapter's latest
        ``ChapterVersion`` rows.
      - ``critic_only``: rerun only the Critic step using the most recent
        draft. Useful when the critic's JSON parser bombed but the prose
        is fine.
      - ``continue_with_fallback``: tell the worker to ignore the
        missing critic report and keep going — the base agent has
        ``allow_json_fallback=True`` for Critic, so this is safe.

    The frontend also stores the chosen mode into ``row.payload`` so
    the worker can read it back at the start of the next run.
    """
    row = await db.get(AgentTask, task_id)
    if row is None:
        raise not_found("AgentTask", task_id)
    body = body or TaskRetryRequest()
    if body.mode == "from_failed_step" and not body.from_step:
        raise bad_request("mode=from_failed_step 需要指定 from_step")
    if body.from_step and body.from_step not in PIPELINE_STEP_ORDER:
        raise bad_request(
            f"from_step '{body.from_step}' 不在流水线中。合法值: {', '.join(PIPELINE_STEP_ORDER)}"
        )
    # Update the row.
    row.status = "pending"
    row.retry_count += 1
    row.error = None
    # Stash the requested mode so the worker can pick the right entry
    # point. The worker reads payload["retry_mode"] and payload["from_step"]
    # at the start of the next run. We rewrite the retry_* keys from
    # scratch each time so a previous retry's settings don't leak into
    # a new one (e.g. a ``critic_only`` after a ``from_failed_step``
    # shouldn't carry over the old ``from_step``).
    payload = dict(row.payload or {})
    payload["retry_mode"] = body.mode
    if body.from_step is not None:
        payload["from_step"] = body.from_step
    else:
        payload.pop("from_step", None)
    payload["reuse_previous_outputs"] = body.reuse_previous_outputs
    row.payload = payload
    await db.flush()
    return {"ok": True, "data": AgentTaskRead.model_validate(row)}


# ----- Round 3 / P1-FUNC-1: task diagnosis -----

def _classify_error(text: str | None) -> str:
    """Bucket the raw error text into one of a few friendly types.
    Kept here (not in a service) because it's used purely for the
    diagnosis response — the worker doesn't need it.
    """
    t = (text or "").lower()
    if not t.strip():
        return "UNKNOWN"
    if "non-json" in t or "json" in t or "jsondecode" in t or "json_object" in t:
        return "JSON_PARSE_FAILED"
    if "401" in t or "unauthorized" in t or "auth" in t:
        return "UNAUTHORIZED"
    if "404" in t or "not found" in t or "no such model" in t:
        return "MODEL_NOT_FOUND"
    if "timeout" in t or "timed out" in t:
        return "TIMEOUT"
    if "connection" in t or "无法连接" in t or "connect" in t:
        return "CONNECTION_FAILED"
    if "rate" in t or "limit" in t or "429" in t:
        return "RATE_LIMITED"
    if "budget" in t or "预算" in t:
        return "BUDGET_EXHAUSTED"
    if "cancelled" in t or "cancel" in t:
        return "CANCELLED"
    if "parse_failed" in t or "无法解析" in t:
        return "JSON_PARSE_FAILED"
    return "UNKNOWN"


_SUGGESTION_TEMPLATES: dict[str, list[dict[str, Any]]] = {
    "JSON_PARSE_FAILED": [
        {
            "type": "from_failed_step",
            "label": "只重跑失败步骤",
            "description": "复用已经通过的 Plan / Draft，从失败的 Critic 重新执行。",
            "risk": "low",
        },
        {
            "type": "continue_with_fallback",
            "label": "使用 fallback Critic 报告继续",
            "description": "CriticAgent 已开启 JSON 兜底，可让流水线忽略坏 JSON 继续走完。",
            "risk": "low",
        },
        {
            "type": "switch_model",
            "label": "切换 Critic 模型",
            "description": "把 Critic 绑到 JSON 更稳的模型（如 deepseek-v4-pro），再重试。",
            "risk": "medium",
        },
    ],
    "UNAUTHORIZED": [
        {
            "type": "open_models",
            "label": "打开模型配置",
            "description": "检查 Provider 的 API Key 是否过期或被撤销。",
            "risk": "low",
        },
    ],
    "MODEL_NOT_FOUND": [
        {
            "type": "open_models",
            "label": "打开模型配置",
            "description": "Base URL 或模型名拼写错误，或该模型已下线。",
            "risk": "low",
        },
    ],
    "TIMEOUT": [
        {
            "type": "from_failed_step",
            "label": "重跑失败步骤",
            "description": "上次超时可能只是网络抖动，复用上游结果再跑一次。",
            "risk": "low",
        },
        {
            "type": "switch_model",
            "label": "切换到更小的模型",
            "description": "调小 max_tokens，或换一个响应更快的模型。",
            "risk": "medium",
        },
    ],
    "CONNECTION_FAILED": [
        {
            "type": "open_models",
            "label": "检查 Provider 连通性",
            "description": "Base URL 不可访问或网络受限，检查代理 / 防火墙。",
            "risk": "low",
        },
    ],
    "RATE_LIMITED": [
        {
            "type": "safe_retry",
            "label": "稍后重试",
            "description": "Provider 触发了限流，等几分钟再试。",
            "risk": "low",
        },
    ],
    "BUDGET_EXHAUSTED": [
        {
            "type": "open_models",
            "label": "调高日预算",
            "description": "在「项目 → 策略」里把 daily_budget_usd 调高，或等第二天再继续。",
            "risk": "low",
        },
    ],
    "CANCELLED": [],
    "UNKNOWN": [
        {
            "type": "view_step",
            "label": "查看 Step 详情",
            "description": "跳到章节 Step 时间线看完整错误。",
            "risk": "low",
        },
        {
            "type": "from_failed_step",
            "label": "从失败处重试",
            "description": "先复跑一次，再决定是否切换模型。",
            "risk": "low",
        },
    ],
}


@router.get("/{task_id}/diagnosis", response_model=APIResponse[TaskDiagnosisRead])
async def task_diagnosis(
    task_id: int, db: AsyncSession = Depends(get_db)
) -> APIResponse[TaskDiagnosisRead]:
    """P1-FUNC-1: structured failure analysis.

    Aggregates the task's AgentStep rows into the same step order the
    pipeline uses, marks each as succeeded / failed / pending /
    skipped, and returns a small set of typed suggestions the dashboard
    can render as action buttons.

    The response is intentionally cheap: one task lookup + one
    step-list query. No additional LLM calls.
    """
    task = await db.get(AgentTask, task_id)
    if task is None:
        raise not_found("AgentTask", task_id)
    steps = (await db.execute(
        select(AgentStep).where(AgentStep.task_id == task_id).order_by(AgentStep.id.asc())
    )).scalars().all()
    # Index the step rows by their step_name so we can fill the rail.
    # A chapter task can run multiple ``rewrite`` rounds — collapse to
    # the last rewrite's status for the rail (most relevant state).
    by_name: dict[str, AgentStep] = {}
    for s in steps:
        if s.step_name in by_name:
            # rewrite rounds: keep the last one
            by_name[s.step_name] = s
        else:
            by_name[s.step_name] = s

    # Find the first failed step (in pipeline order) — that's the one
    # the diagnosis should blame. If no failed step rows survived
    # (P1-3: the pipeline rolls back the whole transaction on failure
    # so failed tasks have no AgentStep rows), fall back to mining the
    # task's error text for an "XxxAgent" mention so the diagnosis is
    # still actionable. We resolve ``failed_step_name`` *before* the
    # rail loop so the ``context_compile`` row can use it to decide
    # whether the failure was early or late.
    failed_step_name: str | None = None
    for name in PIPELINE_STEP_ORDER:
        s = by_name.get(name)
        if s is not None and s.status == "failed":
            failed_step_name = name
            break
    # Track the inferred agent name (regex-derived) so we can fall
    # back to it when no failed step rows exist.
    inferred_failed_agent: str | None = None
    if failed_step_name is None and task.status == "failed":
        # No failed step rows — try to infer from the error text. The
        # base agent writes things like
        # ``CriticAgent 返回非 JSON: ...`` or
        # ``RewriterAgent 返回非 JSON: ...`` when JSON parsing bombs.
        import re
        text_for_scan = task.error or ""
        m = re.search(r"\b([A-Z][A-Za-z]+Agent)\b", text_for_scan)
        if m:
            agent_name = m.group(1)
            # Map agent name to step_name.
            agent_to_step = {
                "PlannerAgent": "plan",
                "DrafterAgent": "draft",
                "CriticAgent": "review",
                "RewriterAgent": "rewrite",
                "ContinuityAgent": "continuity",
                "MemoryUpdateAgent": "memory_update",
                "LearningAgent": "learning",
            }
            step_name_guess = agent_to_step.get(agent_name)
            if step_name_guess:
                failed_step_name = step_name_guess
                inferred_failed_agent = agent_name
    failed_step = by_name.get(failed_step_name) if failed_step_name else None

    # Build the rail. A step is "skipped" when the pipeline aborted
    # before it could run. ``context_compile`` is a service — we add
    # it as a synthetic success row whenever the task got past the
    # planning step.
    rail: list[TaskDiagnosisStep] = []
    saw_failure = False
    saw_success_before_failure = False
    for name in PIPELINE_STEP_ORDER:
        label = STEP_LABELS.get(name, name)
        if name == "context_compile":
            # Heuristic: if the planner ran, context compile succeeded.
            if by_name.get("plan") is not None or by_name.get("draft") is not None:
                rail.append(TaskDiagnosisStep(
                    step_name=name, label=label, status="succeeded",
                    duration_ms=0, cost_usd=0.0,
                ))
            elif task.status == "failed" and failed_step_name is not None and PIPELINE_STEP_ORDER.index(failed_step_name) > 0:
                # The pipeline got past context_compile and only
                # failed later (e.g. in rewrite). Mark context_compile
                # as succeeded so the rail tells the truth: the
                # failure is *later*, not at the very start.
                rail.append(TaskDiagnosisStep(
                    step_name=name, label=label, status="succeeded",
                    duration_ms=0, cost_usd=0.0,
                ))
            elif task.status == "failed":
                # Task failed before the planner ran and we have no
                # evidence the compile succeeded. Mark as failed so
                # the user knows to look at the bible / memory.
                rail.append(TaskDiagnosisStep(
                    step_name=name, label=label, status="failed",
                    error_message=task.error,
                ))
            else:
                rail.append(TaskDiagnosisStep(
                    step_name=name, label=label, status="pending",
                ))
            continue
        s = by_name.get(name)
        if s is None:
            # Synthesise a row for the inferred failed step (no
            # AgentStep row survived but the regex told us where the
            # pipeline died).
            if name == failed_step_name:
                rail.append(TaskDiagnosisStep(
                    step_name=name, label=label, status="failed",
                    agent_name=inferred_failed_agent,
                    error_message=(task.error or "")[:500],
                ))
                saw_failure = True
                continue
            if saw_failure or (task.status == "failed" and not saw_success_before_failure):
                rail.append(TaskDiagnosisStep(
                    step_name=name, label=label, status="skipped",
                ))
            else:
                rail.append(TaskDiagnosisStep(
                    step_name=name, label=label, status="pending",
                ))
            continue
        if s.status == "failed":
            saw_failure = True
            rail.append(TaskDiagnosisStep(
                step_name=name, label=label, status="failed",
                agent_name=s.agent_name,
                started_at=s.started_at, finished_at=s.finished_at,
                duration_ms=s.duration_ms, cost_usd=s.cost_usd,
                error_message=s.error_message,
            ))
        elif s.status == "reused":
            # P15 / P0-RETRY-1: the pipeline kept this step's output
            # from a previous run (the user clicked "重试" with
            # from_failed_step / continue_with_fallback). Render it as
            # a separate "reused" status so the rail shows the truth:
            # no LLM call was made on this attempt. We still record
            # ``agent_name`` and timing so the user can click through
            # to inspect the original output.
            saw_success_before_failure = True or saw_success_before_failure
            rail.append(TaskDiagnosisStep(
                step_name=name, label=label, status="reused",
                agent_name=s.agent_name,
                started_at=s.started_at, finished_at=s.finished_at,
                duration_ms=s.duration_ms, cost_usd=s.cost_usd,
                error_message=s.error_message,
            ))
        else:
            saw_success_before_failure = True or saw_success_before_failure
            # Try to surface the critic score (if the step produced
            # a parsed_output with a ``total`` field).
            score: int | None = None
            parsed = s.parsed_output if isinstance(s.parsed_output, dict) else None
            if isinstance(parsed, dict):
                raw_total = parsed.get("total")
                if isinstance(raw_total, (int, float)):
                    score = int(raw_total)
            rail.append(TaskDiagnosisStep(
                step_name=name, label=label, status="succeeded",
                agent_name=s.agent_name,
                started_at=s.started_at, finished_at=s.finished_at,
                duration_ms=s.duration_ms, cost_usd=s.cost_usd,
                score=score,
            ))

    # Impact = human-readable list of steps that didn't run because of
    # the failure. Skip ones that already ran.
    impact: list[str] = []
    if failed_step_name is not None:
        idx = PIPELINE_STEP_ORDER.index(failed_step_name)
        for later in PIPELINE_STEP_ORDER[idx + 1:]:
            if by_name.get(later) is None:
                impact.append(f"{STEP_LABELS.get(later, later)} 未执行")

    error_type = _classify_error(
        task.error or (failed_step.error_message if failed_step else None)
    )
    error_message = task.error or (failed_step.error_message if failed_step else "（未提供错误信息）")

    # Raw output preview: the failed step's raw_output (first 800 chars).
    raw_preview: str | None = None
    if failed_step is not None and failed_step.raw_output:
        raw_preview = failed_step.raw_output[:800]
    prompt_preview: str | None = None
    if failed_step is not None and failed_step.input_prompt:
        prompt_preview = failed_step.input_prompt[:800]

    # Suggestions: only meaningful for failed tasks. A successful or
    # still-running task has nothing actionable here.
    suggestions: list[TaskDiagnosisSuggestion] = []
    if task.status == "failed":
        templates = _SUGGESTION_TEMPLATES.get(error_type, _SUGGESTION_TEMPLATES["UNKNOWN"])
        suggestions = [
            TaskDiagnosisSuggestion(
                type=t["type"], label=t["label"],
                description=t["description"], risk=t["risk"],
                params={"task_id": task_id},
            )
            for t in templates
        ]
        # Universal "view step" hint so the user can always drill in.
        if task.chapter_id is not None:
            suggestions.append(TaskDiagnosisSuggestion(
                type="view_step",
                label="查看 Step 时间线",
                description="跳到该章节的 Step 详情页，查看原始 prompt / 输出。",
                risk="low",
                params={
                    "task_id": task_id,
                    "project_id": task.project_id,
                    "chapter_id": task.chapter_id,
                },
            ))

    diagnosis = TaskDiagnosisRead(
        task_id=task.id,
        project_id=task.project_id,
        chapter_id=task.chapter_id,
        task_type=task.task_type,
        status=task.status,
        error_type=error_type,
        error_message=error_message,
        failed_agent=inferred_failed_agent or (failed_step.agent_name if failed_step else None),
        failed_step=failed_step_name,
        impact=impact,
        suggestions=suggestions,
        raw_output_preview=raw_preview,
        prompt_preview=prompt_preview,
        steps=rail,
        retry_count=task.retry_count,
    )
    return {"ok": True, "data": diagnosis}
