"""Model Observability API — 模型调用统计与可观测性.

提供:
  GET /api/model-observability/summary          — 指定时间窗口的全局统计
  GET /api/model-observability/events           — 最近调用事件列表
  GET /api/model-observability/providers        — 各 Provider 运行统计
  GET /api/model-observability/runtime-stats    — ModelRuntimeStat 聚合数据
  GET /api/model-observability/models           — 各模型聚合统计
  GET /api/model-observability/agents           — 各 Agent 角色聚合统计
  GET /api/model-observability/slow-requests    — 慢请求列表
  GET /api/model-observability/failures         — 失败事件列表

对应 P0-Model-Failover 方案中的「运行数据看板」需求.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.agent_role import AgentRole, AgentModelBinding
from app.models.model_call_event import ModelCallEvent
from app.models.model_provider import ModelProvider
from app.models.model_runtime import ModelRuntimeStat
from app.schemas import APIResponse
from app.services.agent_run_recorder import get_agent_run_recorder

router = APIRouter(prefix="/model-observability", tags=["model-observability"])


@router.get("/summary", response_model=APIResponse[dict])
async def get_call_summary(
    hours: int = Query(default=24, ge=1, le=168, description="统计窗口（小时）"),
    agent_role_key: str | None = Query(default=None, description="按 Agent 角色过滤"),
    provider_id: int | None = Query(default=None, description="按 Provider ID 过滤"),
    db: AsyncSession = Depends(get_db),
) -> APIResponse[dict]:
    """返回指定时间窗口内的模型调用汇总统计.

    包含: 总调用数、成功率、fallback 率、成本、延迟分位数、按角色分组统计.
    """
    recorder = get_agent_run_recorder()
    data = await recorder.get_summary(
        db,
        hours=hours,
        agent_role_key=agent_role_key,
        provider_id=provider_id,
    )
    return {"ok": True, "data": data}


@router.get("/events", response_model=APIResponse[list])
async def get_recent_events(
    limit: int = Query(default=50, ge=1, le=500),
    agent_role_key: str | None = Query(default=None),
    provider_id: int | None = Query(default=None),
    status: str | None = Query(default=None, description="success/failed/fallback_success/fallback_failed"),
    event_type: str | None = Query(default=None, description="事件类型过滤"),
    event_category: str | None = Query(default=None, description="事件分类过滤"),
    level: str | None = Query(default=None, description="严重级别过滤"),
    model_name: str | None = Query(default=None, description="模型名称过滤"),
    project_id: int | None = Query(default=None, description="项目ID过滤"),
    chapter_id: int | None = Query(default=None, description="章节ID过滤"),
    db: AsyncSession = Depends(get_db),
) -> APIResponse[list]:
    """返回最近的模型调用事件列表.

    可按 agent_role_key / provider_id / status / event_type / event_category / level / model_name / project_id / chapter_id 过滤.
    """
    recorder = get_agent_run_recorder()
    events = await recorder.get_recent_events(
        db,
        limit=limit,
        agent_role_key=agent_role_key,
        provider_id=provider_id,
        status=status,
        event_type=event_type,
        event_category=event_category,
        level=level,
        model_name=model_name,
        project_id=project_id,
        chapter_id=chapter_id,
    )
    return {"ok": True, "data": events}


@router.get("/providers", response_model=APIResponse[list])
async def get_provider_stats(
    hours: int = Query(default=24, ge=1, le=168),
    db: AsyncSession = Depends(get_db),
) -> APIResponse[list]:
    """返回各 Provider 的运行统计 + 当前健康状态.

    包含: 调用量、成功率、fallback 量、总成本、平均延迟.
    """
    recorder = get_agent_run_recorder()
    stats = await recorder.get_provider_stats(db, hours=hours)
    return {"ok": True, "data": stats}


@router.get("/runtime-stats", response_model=APIResponse[list])
async def get_runtime_stats(
    agent_role_key: str | None = Query(default=None),
    provider_id: int | None = Query(default=None),
    window: str = Query(default="rolling_24h", description="rolling_24h / rolling_7d"),
    db: AsyncSession = Depends(get_db),
) -> APIResponse[list]:
    """返回 ModelRuntimeStat 聚合数据.

    ModelRuntimeStat 由 ModelCallRecorder 每次调用后实时更新,
    是 ModelSelector 评分的数据来源.
    """
    q = select(ModelRuntimeStat)
    if agent_role_key:
        q = q.where(ModelRuntimeStat.agent_role_key == agent_role_key)
    if provider_id:
        q = q.where(ModelRuntimeStat.provider_id == provider_id)
    if window:
        q = q.where(ModelRuntimeStat.window == window)

    stats = (await db.execute(q)).scalars().all()
    data = [
        {
            "id": s.id,
            "provider_id": s.provider_id,
            "model_name": s.model_name,
            "agent_role_key": s.agent_role_key,
            "window": s.window,
            "total_calls": s.total_calls,
            "success_calls": s.success_calls,
            "failed_calls": s.failed_calls,
            "fallback_calls": s.fallback_calls,
            "success_rate": round(s.success_calls / s.total_calls, 4) if s.total_calls else 0.0,
            "avg_latency_ms": s.avg_latency_ms,
            "json_parse_failures": s.json_parse_failures,
            "total_cost_usd": s.total_cost_usd,
            "last_used_at": s.last_used_at.isoformat() if s.last_used_at else None,
            "updated_at": s.updated_at.isoformat() if s.updated_at else None,
        }
        for s in stats
    ]
    return {"ok": True, "data": data}


# ── P0-observability-rework: 新增端点 ──────────────────────────


@router.get("/models", response_model=APIResponse[list])
async def get_model_stats(
    hours: int = Query(default=24, ge=1, le=168),
    provider_id: int | None = Query(default=None),
    agent_role_key: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    """返回各模型的聚合统计.

    按 model_name + provider_id 分组, 返回调用量、成功率、延迟、成本等.
    """
    since = datetime.utcnow() - timedelta(hours=hours)

    # 加载事件
    q = select(ModelCallEvent).where(ModelCallEvent.created_at >= since)
    if provider_id:
        q = q.where(ModelCallEvent.provider_id == provider_id)
    if agent_role_key:
        q = q.where(ModelCallEvent.agent_role_key == agent_role_key)
    events = (await db.execute(q)).scalars().all()

    # 按 (provider_id, model_name) 分组
    groups: dict[tuple[int | None, str | None], list[ModelCallEvent]] = {}
    for e in events:
        key = (e.provider_id, e.model_name)
        groups.setdefault(key, []).append(e)

    # 加载 provider 名称映射
    providers = (await db.execute(select(ModelProvider))).scalars().all()
    provider_map = {p.id: p.name for p in providers}

    result = []
    for (pid, mname), evts in groups.items():
        total = len(evts)
        success = sum(1 for e in evts if e.status in ("success", "fallback_success"))
        latencies = sorted(e.latency_ms for e in evts if e.latency_ms is not None)
        avg_lat = int(sum(latencies) / len(latencies)) if latencies else None
        # P95 近似: 取排序后 95% 位置的值
        if len(latencies) >= 20:
            p95_idx = min(int(len(latencies) * 0.95), len(latencies) - 1)
            p95_lat = latencies[p95_idx]
        elif latencies:
            p95_lat = latencies[-1]  # 不足20条用最大值
        else:
            p95_lat = None

        total_input = sum(e.input_tokens for e in evts)
        total_output = sum(e.output_tokens for e in evts)
        total_cost = sum(e.cost_usd for e in evts)

        used_by = sorted({e.agent_role_key for e in evts if e.agent_role_key}) or None
        empty_count = sum(1 for e in evts if e.event_type == "empty_output")
        json_fail = sum(1 for e in evts if e.event_type == "json_parse_failed")
        qg_fail = sum(1 for e in evts if e.event_type == "quality_gate_failed")

        last_used = max((e.created_at for e in evts), default=None)
        last_err = None
        for e in reversed(evts):
            if e.status in ("failed", "fallback_failed") and e.failure_message:
                last_err = e.failure_message[:200]
                break

        result.append({
            "provider_id": pid,
            "provider_name": provider_map.get(pid),
            "model_name": mname,
            "call_count": total,
            "success_rate": round(success / total, 4) if total else 0.0,
            "avg_latency_ms": avg_lat,
            "p95_latency_ms": p95_lat,
            "input_tokens": total_input,
            "output_tokens": total_output,
            "cost_usd": round(total_cost, 6),
            "used_by_agents": used_by,
            "empty_output_count": empty_count,
            "json_parse_failed_count": json_fail,
            "quality_gate_failed_count": qg_fail,
            "last_used_at": last_used.isoformat() if last_used else None,
            "last_error_message": last_err,
        })

    result.sort(key=lambda x: x["call_count"], reverse=True)
    return {"ok": True, "data": result}


@router.get("/agents", response_model=APIResponse[list])
async def get_agent_stats(
    hours: int = Query(default=24, ge=1, le=168),
    project_id: int | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    """返回各 Agent 角色的聚合统计.

    按 agent_role_key 分组, join agent_roles 获取绑定信息.
    """
    since = datetime.utcnow() - timedelta(hours=hours)

    # 加载事件
    q = select(ModelCallEvent).where(ModelCallEvent.created_at >= since)
    if project_id:
        q = q.where(ModelCallEvent.project_id == project_id)
    events = (await db.execute(q)).scalars().all()

    # 按 agent_role_key 分组
    groups: dict[str, list[ModelCallEvent]] = {}
    for e in events:
        rk = e.agent_role_key or "unknown"
        groups.setdefault(rk, []).append(e)

    # 加载 AgentRole 信息
    roles = (await db.execute(select(AgentRole))).scalars().all()
    role_map = {r.key: r for r in roles}

    # 加载 AgentModelBinding
    bindings = (await db.execute(select(AgentModelBinding))).scalars().all()
    binding_map = {b.agent_role_id: b for b in bindings}
    # role key → binding
    role_key_to_binding: dict[str, AgentModelBinding] = {}
    for r in roles:
        b = binding_map.get(r.id)
        if b:
            role_key_to_binding[r.key] = b

    # 加载 provider 名称映射
    providers = (await db.execute(select(ModelProvider))).scalars().all()
    provider_map = {p.id: p.name for p in providers}

    result = []
    for rk, evts in groups.items():
        total = len(evts)
        success = sum(1 for e in evts if e.status in ("success", "fallback_success"))
        latencies = [e.latency_ms for e in evts if e.latency_ms is not None]
        avg_lat = int(sum(latencies) / len(latencies)) if latencies else None

        total_tokens = sum(e.input_tokens + e.output_tokens for e in evts)
        total_cost = sum(e.cost_usd for e in evts)

        role = role_map.get(rk)
        binding = role_key_to_binding.get(rk)

        current_provider_name = None
        current_model_name = None
        selection_mode = None
        fallback_strategy = None
        if binding:
            selection_mode = binding.selection_mode
            fallback_strategy = binding.auto_strategy
            current_provider_name = provider_map.get(binding.provider_id)
            current_model_name = binding.last_selected_model_name or binding.model_name

        # 最近一次运行状态
        last_status = None
        last_error = None
        for e in reversed(evts):
            if e.status in ("success", "failed", "fallback_success", "fallback_failed"):
                last_status = "success" if e.status in ("success", "fallback_success") else "failed"
                if e.failure_message:
                    last_error = e.failure_message[:200]
                break

        result.append({
            "agent_role_key": rk,
            "agent_role_name": role.display_name if role else rk,
            "category": role.category if role else None,
            "current_provider_name": current_provider_name,
            "current_model_name": current_model_name,
            "binding_mode": selection_mode,
            "fallback_strategy": fallback_strategy,
            "call_count": total,
            "success_rate": round(success / total, 4) if total else 0.0,
            "avg_latency_ms": avg_lat,
            "total_tokens": total_tokens,
            "cost_usd": round(total_cost, 6),
            "running_task_id": None,
            "last_run_status": last_status,
            "last_error_message": last_error,
        })

    result.sort(key=lambda x: x["call_count"], reverse=True)
    return {"ok": True, "data": result}


@router.get("/slow-requests", response_model=APIResponse[list])
async def get_slow_requests(
    hours: int = Query(default=24, ge=1, le=168),
    threshold_ms: int = Query(default=10000, ge=1000),
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """返回延迟超过阈值的请求列表, 按 latency_ms 降序."""
    since = datetime.utcnow() - timedelta(hours=hours)
    q = (
        select(ModelCallEvent)
        .where(
            ModelCallEvent.created_at >= since,
            ModelCallEvent.latency_ms >= threshold_ms,
        )
        .order_by(desc(ModelCallEvent.latency_ms))
        .limit(limit)
    )
    events = (await db.execute(q)).scalars().all()
    data = [_serialize_event(e) for e in events]
    return {"ok": True, "data": data}


@router.get("/failures", response_model=APIResponse[list])
async def get_failures(
    hours: int = Query(default=24, ge=1, le=168),
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    """返回失败事件列表, 包含 failed/fallback_failed 以及 fallback_success+level=warning."""
    since = datetime.utcnow() - timedelta(hours=hours)
    q = (
        select(ModelCallEvent)
        .where(
            ModelCallEvent.created_at >= since,
            (ModelCallEvent.status.in_(["failed", "fallback_failed"]))
            | ((ModelCallEvent.status == "fallback_success") & (ModelCallEvent.level == "warning")),
        )
        .order_by(desc(ModelCallEvent.created_at))
        .limit(limit)
    )
    events = (await db.execute(q)).scalars().all()
    data = [_serialize_event(e) for e in events]
    return {"ok": True, "data": data}


# ── 内部辅助 ──


def _serialize_event(e: ModelCallEvent) -> dict[str, Any]:
    """将 ModelCallEvent 序列化为 dict, 包含所有新老字段."""
    return {
        "id": e.id,
        "provider_id": e.provider_id,
        "model_name": e.model_name,
        "agent_role_key": e.agent_role_key,
        "project_id": e.project_id,
        "task_id": e.task_id,
        "chapter_id": e.chapter_id,
        "step_key": e.step_key,
        "provider_name": e.provider_name,
        "selection_mode": e.selection_mode,
        "selection_score": e.selection_score,
        "selection_reason": e.selection_reason,
        "status": e.status,
        "failure_type": e.failure_type,
        "failure_message": e.failure_message,
        "latency_ms": e.latency_ms,
        "input_tokens": e.input_tokens,
        "output_tokens": e.output_tokens,
        "cost_usd": e.cost_usd,
        "event_type": e.event_type,
        "event_category": e.event_category,
        "level": e.level,
        "fallback_from_provider": e.fallback_from_provider,
        "fallback_from_model": e.fallback_from_model,
        "fallback_to_provider": e.fallback_to_provider,
        "fallback_to_model": e.fallback_to_model,
        "summary": e.summary,
        "detail_json": e.detail_json,
        "cache_hit": e.cache_hit,
        "request_id": e.request_id,
        "error_code": e.error_code,
        "created_at": e.created_at.isoformat() if e.created_at else None,
    }
