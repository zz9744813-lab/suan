"""Model Observability API — 模型调用统计与可观测性.

提供:
  GET /api/observability/summary          — 指定时间窗口的全局统计
  GET /api/observability/events           — 最近调用事件列表
  GET /api/observability/providers        — 各 Provider 运行统计
  GET /api/observability/runtime-stats    — ModelRuntimeStat 聚合数据

对应 P0-Model-Failover 方案中的「运行数据看板」需求.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
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
    db: AsyncSession = Depends(get_db),
) -> APIResponse[list]:
    """返回最近的模型调用事件列表.

    可按 agent_role_key / provider_id / status 过滤.
    """
    recorder = get_agent_run_recorder()
    events = await recorder.get_recent_events(
        db,
        limit=limit,
        agent_role_key=agent_role_key,
        provider_id=provider_id,
        status=status,
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
