"""Workbench 聚合状态接口 (P0 返工)

- GET /api/workbench/live-state : 五个生产域的当前状态
  （写作 / 拆书 / 模型 / 讨论 / 记忆）— 替代前端到处拉 tasks/worker/steps 拼 UI
- GET /api/workbench/top-stats  : 顶部状态栏数字（今日产出 / 当前运行 / 堵塞 / API 健康 / 成本）

设计原则：
1. **不返回内部子任务**。domain=writing|deepstudy|model|discussion|memory
2. **不返回 AgentStep 表**。只返回对外可读的状态文本
3. 内部子任务 comment_cleanup / study_character / reader_review 等
   通过 visibility="user" 过滤掉
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.task import AgentTask, WorkerStatus
from app.schemas import APIResponse
from app.services.llm.client import LLMClient

router = APIRouter(prefix="/workbench", tags=["workbench"])


# 域定义 — 与 P0 返工方案 §0 一致
DOMAINS: list[dict[str, str]] = [
    {"key": "writing", "label": "写作产线", "icon": "✍"},
    {"key": "deepstudy", "label": "拆书产线", "icon": "📚"},
    {"key": "model", "label": "模型路由", "icon": "🧠"},
    {"key": "discussion", "label": "讨论反馈", "icon": "☕"},
    {"key": "memory", "label": "记忆系统", "icon": "💾"},
]


def _domain_state_for(domain: str, tasks: list[AgentTask]) -> dict[str, Any]:
    """把一个域下的 user-visibility 任务聚合成一张状态卡数据。"""
    running = [t for t in tasks if t.status == "running"]
    failed = [t for t in tasks if t.status == "failed"]
    succeeded_recent = [
        t for t in tasks
        if t.status == "succeeded"
        and t.finished_at is not None
        and t.finished_at >= datetime.utcnow() - timedelta(hours=24)
    ]

    if running:
        cur = running[0]
        progress = (
            round(100 * cur.progress_current / cur.progress_total)
            if cur.progress_total > 0
            else None
        )
        return {
            "status": "running",
            "current_agent": cur.task_kind or cur.task_type or "Worker",
            "current_action": cur.display_title or _default_action(cur),
            "progress": progress,
            "artifact_summary": _summary_text(cur),
            "error": None,
            "task_id": cur.id,
            "started_at": cur.started_at.isoformat() if cur.started_at else None,
        }
    if failed:
        last_fail = failed[0]
        return {
            "status": "failed",
            "current_agent": last_fail.task_kind or last_fail.task_type or "—",
            "current_action": last_fail.display_title or "上次运行未成功",
            "progress": 0,
            "artifact_summary": _summary_text(last_fail),
            "error": (last_fail.error or "")[:200] or None,
            "task_id": last_fail.id,
            "started_at": last_fail.started_at.isoformat() if last_fail.started_at else None,
        }
    # 阻塞判定：超过 1 分钟没有 succeeded 也没有 running → 视为堵塞
    if succeeded_recent:
        last = succeeded_recent[0]
        return {
            "status": "idle",
            "current_agent": "—",
            "current_action": f"上次完成: {last.display_title or last.task_type}",
            "progress": 100,
            "artifact_summary": _summary_text(last),
            "error": None,
            "task_id": last.id,
            "started_at": last.finished_at.isoformat() if last.finished_at else None,
        }
    return {
        "status": "idle",
        "current_agent": "—",
        "current_action": "暂无任务",
        "progress": None,
        "artifact_summary": "—",
        "error": None,
        "task_id": None,
        "started_at": None,
    }


def _default_action(t: AgentTask) -> str:
    kind = (t.task_kind or t.task_type or "").lower()
    if "draft" in kind:
        return f"正在写第 {t.chapter_id or '?'} 章初稿"
    if "rewrite" in kind:
        return f"正在改稿 第 {t.chapter_id or '?'} 章"
    if "review" in kind or "critic" in kind:
        return f"正在评审 第 {t.chapter_id or '?'} 章"
    if "study_character" in kind:
        return "正在拆解人物"
    if "study_event" in kind:
        return "正在抽取事件"
    if "study_relation" in kind:
        return "正在抽取关系"
    if "study_technique" in kind:
        return "正在抽取写作技巧"
    if "study_behavior" in kind:
        return "正在抽取行为模式"
    if "study_chapterize" in kind:
        return "正在分章"
    if "study_foreshadow" in kind:
        return "正在抽取伏笔"
    if "graph_materialise" in kind:
        return "正在物化图谱"
    if "discussion" in kind:
        return "正在组织讨论"
    if "memory" in kind:
        return "正在整理记忆"
    return t.task_type


def _summary_text(t: AgentTask) -> str:
    """把任务产物的"行数 / 节点数 / Token / 成本"等聚合成一句人话。"""
    parts: list[str] = []
    sj = t.summary_json or {}
    if isinstance(sj, dict):
        for k, v in sj.items():
            parts.append(f"{k} {v}")
    if t.input_tokens or t.output_tokens:
        parts.append(
            f"{(t.input_tokens + t.output_tokens) / 1000:.1f}k tokens"
        )
    if t.cost_usd:
        parts.append(f"${t.cost_usd:.4f}")
    if t.progress_total > 0:
        parts.append(f"{t.progress_current}/{t.progress_total}")
    return " · ".join(parts) if parts else "—"


@router.get("/live-state", response_model=APIResponse[dict[str, Any]])
async def live_state(db: AsyncSession = Depends(get_db)) -> APIResponse[dict[str, Any]]:
    """返回 5 个生产域的当前状态卡数据。

    行为契约：
    1. 只看 visibility="user" 的任务（内部子任务不返回）
    2. domain 字段未填的 fallback 到 task_type 归类
    """
    # 1) 拉所有 user-visibility 任务（最近 7 天内，避免大表扫描）
    #    排除内部子任务 (P0 返工 Phase 1.3)：comment_cleanup / study_* / graph_materialise
    #    这些任务的 visibility 字段被历史代码标成 "user"，导致泄漏到用户视图
    INTERNAL_TASK_TYPES = (
        "comment_cleanup", "study_character", "study_event", "study_relation",
        "study_technique", "study_behavior", "study_foreshadow", "study_chapterize",
        "graph_materialise", "study", "study_bulk", "chapterize", "study_material",
    )
    cutoff = datetime.utcnow() - timedelta(days=7)
    stmt = (
        select(AgentTask)
        .where(AgentTask.visibility == "user")
        .where(AgentTask.task_type.notin_(INTERNAL_TASK_TYPES))
        .where(AgentTask.created_at >= cutoff)
        .order_by(AgentTask.id.desc())
        .limit(500)
    )
    rows = (await db.execute(stmt)).scalars().all()

    # 2) 按域分桶
    by_domain: dict[str, list[AgentTask]] = {d["key"]: [] for d in DOMAINS}
    for t in rows:
        d = (t.domain or "writing").lower()
        if d not in by_domain:
            d = "writing"
        by_domain[d].append(t)

    # 3) 聚合每域
    domains_out: dict[str, Any] = {}
    for d in DOMAINS:
        domains_out[d["key"]] = {
            "label": d["label"],
            "icon": d["icon"],
            **_domain_state_for(d["key"], by_domain[d["key"]]),
        }

    # 4) 当前主任务（单条最强信号）：选最近 1 个 running
    main_task = next((t for t in rows if t.status == "running"), None)
    main_task_out = None
    if main_task is not None:
        main_task_out = {
            "id": main_task.id,
            "title": main_task.display_title or _default_action(main_task),
            "domain": (main_task.domain or "writing"),
            "task_type": main_task.task_type,
            "task_kind": main_task.task_kind,
            "progress_current": main_task.progress_current,
            "progress_total": main_task.progress_total,
            "started_at": main_task.started_at.isoformat() if main_task.started_at else None,
        }

    return {
        "ok": True,
        "data": {
            "domains": domains_out,
            "main_task": main_task_out,
            "as_of": datetime.utcnow().isoformat() + "Z",
        },
    }


@router.get("/top-stats", response_model=APIResponse[dict[str, Any]])
async def top_stats(db: AsyncSession = Depends(get_db)) -> APIResponse[dict[str, Any]]:
    """顶部状态栏数字：今日产出 / 当前运行 / 堵塞 / API 健康 / 成本。"""
    now = datetime.utcnow()
    today_start = datetime(now.year, now.month, now.day)

    # 1) 今日 succeeded 任务数
    today_succeeded = (await db.execute(
        select(func.count(AgentTask.id))
        .where(AgentTask.visibility == "user")
        .where(AgentTask.status == "succeeded")
        .where(AgentTask.finished_at != None)
        .where(AgentTask.finished_at >= today_start)
    )).scalar_one()

    # 2) 当前 running
    running = (await db.execute(
        select(func.count(AgentTask.id))
        .where(AgentTask.visibility == "user")
        .where(AgentTask.status == "running")
    )).scalar_one()

    # 3) 堵塞：failed 但还没 retry 完成的
    blocked = (await db.execute(
        select(func.count(AgentTask.id))
        .where(AgentTask.visibility == "user")
        .where(AgentTask.status == "failed")
        .where(AgentTask.retry_count < AgentTask.max_retries)
    )).scalar_one()

    # 4) 今日成本
    today_cost = (await db.execute(
        select(func.coalesce(func.sum(AgentTask.cost_usd), 0.0))
        .where(AgentTask.finished_at != None)
        .where(AgentTask.finished_at >= today_start)
    )).scalar_one()

    # 5) API 健康 — 用 WorkerStatus.last_heartbeat_at 推断
    worker = (await db.execute(select(WorkerStatus).where(WorkerStatus.id == 1))).scalar_one_or_none()
    api_healthy = True
    api_status = "ok"
    if worker is not None:
        if worker.last_heartbeat_at is None:
            api_healthy = False
            api_status = "no_heartbeat"
        else:
            age = (now - worker.last_heartbeat_at).total_seconds()
            if age > 60:
                api_healthy = False
                api_status = f"stale_{int(age)}s"
            else:
                api_status = f"ok_{int(age)}s"

    # 6) 今日字数（来自 worker_status）
    today_words = int(worker.today_words) if worker is not None else 0

    return {
        "ok": True,
        "data": {
            "today_succeeded": int(today_succeeded),
            "running": int(running),
            "blocked": int(blocked),
            "today_cost_usd": float(today_cost),
            "today_words": today_words,
            "api_healthy": api_healthy,
            "api_status": api_status,
            "worker_state": (worker.state if worker else "unknown"),
        },
    }
