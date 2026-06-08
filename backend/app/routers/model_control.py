"""P0-Model-Config: /api/model-control 路由.

端点点:
- GET  /overview                          — Provider 总览 + Agent 状态
- GET  /providers/{id}                    — Provider 第二层详情
- POST /providers/{id}/models/{name}/probe — 单模型探测
- POST /providers/{id}/probe-all          — Provider 全模型探测
- POST /probe-all                         — 全量探测所有 Provider
"""

from __future__ import annotations

import time
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db, session_scope
from app.models.agent_role import AgentModelBinding, AgentRole
from app.models.model_provider import ModelProvider
from app.models.model_health import ModelHealthSnapshot, ModelRouteEvent

router = APIRouter(prefix="/model-control", tags=["model-control"])


# ============================================================
# Overview
# ============================================================

@router.get("/overview")
async def get_overview(db: AsyncSession = Depends(get_db)):
    """第一层总览：Provider 列表 + Agent 状态 + 健康摘要."""
    providers_raw = (await db.execute(
        select(ModelProvider).order_by(ModelProvider.id.asc())
    )).scalars().all()

    providers_list = []
    for p in providers_raw:
        # Count health snapshots
        snapshots = (await db.execute(
            select(ModelHealthSnapshot).where(
                ModelHealthSnapshot.provider_id == p.id
            )
        )).scalars().all()

        healthy = sum(1 for s in snapshots if s.status == "healthy")
        failing = sum(1 for s in snapshots if s.status == "failing")

        providers_list.append({
            "id": p.id,
            "name": p.name,
            "base_url": p.base_url,
            "enabled": p.enabled,
            "default_model": p.default_model,
            "model_count": len(p.model_list or []),
            # P-Auto-Config: AutoConfigureModal 在前端做"轻量模型
            # 启发" (匹配 mini/flash/lite/small 关键字), 需要拿到
            # 完整 ``model_list`` 字符串数组. ``model_count`` 只能
            # 告诉数量, 拿不到名字.
            "model_list": p.model_list or [],
            "healthy_count": healthy,
            "failing_count": failing,
            "success_rate": p.success_rate_24h or 1.0,
            "avg_latency_ms": p.avg_latency_ms,
            "circuit_state": p.circuit_state or "closed",
            "is_stub": p.base_url == "mock://local",
        })

    # Agent bindings
    roles = (await db.execute(
        select(AgentRole).where(AgentRole.visible_in_matrix == True)
    )).scalars().all()

    agents_list = []
    mock_count = locked_count = auto_count = 0

    for role in roles:
        binding = (await db.execute(
            select(AgentModelBinding).where(
                AgentModelBinding.agent_role_id == role.id
            )
        )).scalar_one_or_none()

        provider_name = None
        current_model = None
        if binding and binding.provider_id:
            provider = (await db.execute(
                select(ModelProvider).where(ModelProvider.id == binding.provider_id)
            )).scalar_one_or_none()
            provider_name = provider.name if provider else None

        mode = "auto"
        if binding:
            mode = binding.binding_mode or (
                "manual_with_fallback" if binding.selection_mode != "auto" else "auto"
            )
            if binding.provider_id:
                provider = (await db.execute(
                    select(ModelProvider).where(ModelProvider.id == binding.provider_id)
                )).scalar_one_or_none()
                provider_name = provider.name if provider else None
                current_model = binding.model_name

        if mode == "locked":
            locked_count += 1
        elif mode == "auto":
            auto_count += 1

        if binding and binding.provider_id:
            p = next((pp for pp in providers_raw if pp.id == binding.provider_id), None)
            if p and p.base_url == "mock://local":
                mock_count += 1

        agents_list.append({
            "role_id": role.id,
            "role_key": role.key,
            "display_name": role.display_name,
            "category": role.category,
            "enabled": role.enabled,
            "binding_mode": mode,
            "provider_name": provider_name,
            "current_model": current_model,
            "is_locked": mode == "locked",
            "allow_fallback": binding.allow_fallback if binding else True,
            "recent_status": "idle",  # derived from AgentRun
        })

    # Summary stats
    all_snapshots = (await db.execute(
        select(ModelHealthSnapshot)
    )).scalars().all()

    return {
        "ok": True,
        "data": {
            "provider_count": len(providers_raw),
            "enabled_provider_count": sum(1 for p in providers_raw if p.enabled),
            "model_count": len(all_snapshots),
            "healthy_model_count": sum(1 for s in all_snapshots if s.status == "healthy"),
            "failing_model_count": sum(1 for s in all_snapshots if s.status == "failing"),
            "mock_binding_count": mock_count,
            "locked_agent_count": locked_count,
            "auto_agent_count": auto_count,
            "providers": providers_list,
            "agents": agents_list,
        },
        "error": None,
    }


# ============================================================
# Provider Detail (第二层)
# ============================================================

@router.get("/providers/{provider_id}")
async def get_provider_detail(
    provider_id: int,
    db: AsyncSession = Depends(get_db),
):
    """第二层：某 Provider 的模型、Fallback、调用记录、绑定 Agent."""
    provider = (await db.execute(
        select(ModelProvider).where(ModelProvider.id == provider_id)
    )).scalar_one_or_none()

    if not provider:
        return {"ok": False, "data": None, "error": "Provider not found"}

    # Models
    snapshots = (await db.execute(
        select(ModelHealthSnapshot).where(
            ModelHealthSnapshot.provider_id == provider_id
        )
    )).scalars().all()

    models_list = []
    snapshot_names = set()
    for s in snapshots:
        snapshot_names.add(s.model_name)
        models_list.append({
            "model_name": s.model_name,
            "status": s.status,
            "health_score": s.health_score,
            "success_rate": s.success_rate,
            "avg_latency_ms": s.avg_latency_ms,
            "supports_json": s.supports_json,
            "supports_text": s.supports_text,
            "last_error_message": s.last_error_message,
            "probe_count": s.probe_count,
            "consecutive_failures": s.consecutive_failures,
            "input_price_per_million": s.input_price_per_million,
            "output_price_per_million": s.output_price_per_million,
        })

    # Add models from model_list that don't have snapshots yet
    if provider.model_list:
        for m in provider.model_list:
            if m not in snapshot_names:
                models_list.append({
                    "model_name": m,
                    "status": "unknown",
                    "health_score": 0.0,
                    "success_rate": 0.0,
                    "avg_latency_ms": 0,
                    "supports_json": False,
                    "supports_text": True,
                    "last_error_message": None,
                    "probe_count": 0,
                    "consecutive_failures": 0,
                    "input_price_per_million": None,
                    "output_price_per_million": None,
                })

    # Route events (最近 50 条)
    route_events = (await db.execute(
        select(ModelRouteEvent)
        .where(
            (ModelRouteEvent.selected_provider_id == provider_id)
            | (ModelRouteEvent.attempted_provider_id == provider_id)
        )
        .order_by(ModelRouteEvent.created_at.desc())
        .limit(50)
    )).scalars().all()

    events_list = []
    for e in route_events:
        events_list.append({
            "id": e.id,
            "agent_role_key": e.agent_role_key,
            "binding_mode": e.binding_mode,
            "selected_model_name": e.selected_model_name,
            "route_reason": e.route_reason,
            "locked": e.locked,
            "fallback_used": e.fallback_used,
            "health_score": e.health_score,
            "error_message": e.error_message,
            "created_at": e.created_at.isoformat() if e.created_at else None,
        })

    # Bound agents
    bindings = (await db.execute(
        select(AgentModelBinding).where(
            (AgentModelBinding.provider_id == provider_id)
            | (AgentModelBinding.locked_provider_id == provider_id)
        )
    )).scalars().all()

    bound_agents = []
    for b in bindings:
        role = (await db.execute(
            select(AgentRole).where(AgentRole.id == b.agent_role_id)
        )).scalar_one_or_none()
        mode = b.binding_mode or (
            "manual_with_fallback" if b.selection_mode != "auto" else "auto"
        )
        bound_agents.append({
            "role_id": b.agent_role_id,
            "role_key": role.key if role else None,
            "display_name": role.display_name if role else None,
            "binding_mode": mode,
            "model_name": b.model_name,
            "is_locked": mode == "locked",
        })

    return {
        "ok": True,
        "data": {
            "provider": {
                "id": provider.id,
                "name": provider.name,
                "base_url": provider.base_url,
                "enabled": provider.enabled,
                "default_model": provider.default_model,
                "model_count": len(provider.model_list or []),
                "is_stub": provider.base_url == "mock://local",
            },
            "models": models_list,
            "route_events": events_list,
            "bound_agents": bound_agents,
        },
        "error": None,
    }


# ============================================================
# Probe
# ============================================================

@router.post("/providers/{provider_id}/models/{model_name:path}/probe")
async def probe_single_model(
    provider_id: int,
    model_name: str,
    db: AsyncSession = Depends(get_db),
):
    """探测单个模型."""
    provider = (await db.execute(
        select(ModelProvider).where(ModelProvider.id == provider_id)
    )).scalar_one_or_none()

    if not provider:
        return {"ok": False, "data": None, "error": "Provider not found"}

    from app.services.model_probe_service import ModelProbeService
    svc = ModelProbeService()

    result = await svc.probe_model(
        provider_id=provider.id,
        model_name=model_name,
        base_url=provider.base_url,
        api_key=provider.api_key or "",
    )

    from app.services.model_health_monitor import ModelHealthMonitor
    monitor = ModelHealthMonitor()
    await monitor.record_call_result(
        provider_id=provider.id,
        model_name=model_name,
        success=result.ok,
        latency_ms=result.latency_ms,
        error_code=result.error_code,
        error_message=result.error_message,
    )

    return {
        "ok": True,
        "data": {
            "model_name": model_name,
            "status": result.status,
            "latency_ms": result.latency_ms,
            "has_text": result.has_text,
            "has_json": result.has_json,
            "error_code": result.error_code,
            "error_message": result.error_message,
            "health_score": result.health_score,
            "raw_preview": result.raw_preview,
        },
        "error": None,
    }


@router.post("/providers/{provider_id}/probe-all")
async def probe_provider_all(
    provider_id: int,
    db: AsyncSession = Depends(get_db),
):
    """探测 Provider 下所有模型."""
    from app.services.model_health_monitor import ModelHealthMonitor
    monitor = ModelHealthMonitor()
    results = await monitor.probe_provider_models(provider_id)
    return {
        "ok": True,
        "data": {
            "provider_id": provider_id,
            "total": len(results),
            "passed": sum(1 for r in results if r.get("status") == "healthy"),
            "failed": sum(1 for r in results if r.get("status") == "failing"),
            "items": results,
        },
        "error": None,
    }


@router.post("/probe-all")
async def probe_all():
    """全量探测所有 Provider 的模型."""
    from app.services.model_health_monitor import ModelHealthMonitor
    monitor = ModelHealthMonitor()
    summary = await monitor.probe_all_providers()
    return {"ok": True, "data": summary, "error": None}


# ============================================================
# Route events (debug / audit)
# ============================================================

@router.get("/route-events")
async def list_route_events(
    limit: int = Query(default=100, le=500),
    agent_role_key: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """列出最近的模型路由事件."""
    q = select(ModelRouteEvent).order_by(ModelRouteEvent.created_at.desc())
    if agent_role_key:
        q = q.where(ModelRouteEvent.agent_role_key == agent_role_key)
    rows = (await db.execute(q.limit(limit))).scalars().all()

    return {
        "ok": True,
        "data": [{
            "id": r.id,
            "agent_role_key": r.agent_role_key,
            "binding_mode": r.binding_mode,
            "route_reason": r.route_reason,
            "selected_model_name": r.selected_model_name,
            "locked": r.locked,
            "fallback_used": r.fallback_used,
            "health_score": r.health_score,
            "latency_ms": r.latency_ms,
            "error_message": r.error_message,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        } for r in rows],
        "error": None,
    }
