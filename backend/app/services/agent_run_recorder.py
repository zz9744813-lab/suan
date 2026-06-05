"""AgentRunRecorder: 统一记录 Agent 每次调用的运行摘要.

在 Worker/Pipeline 层面调用, 聚合 model_call_events 并写入 AgentStep 的
统计字段, 同时提供查询接口供 observability 路由使用.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import and_, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.model_call_event import ModelCallEvent
from app.models.model_runtime import ModelRuntimeStat
from app.models.model_provider import ModelProvider

logger = logging.getLogger(__name__)


class AgentRunRecorder:
    """查询 model_call_events 聚合数据, 供 Observability API 使用."""

    # ── 聚合查询 ──────────────────────────────────────────────────

    async def get_summary(
        self,
        db: AsyncSession,
        *,
        hours: int = 24,
        agent_role_key: str | None = None,
        provider_id: int | None = None,
    ) -> dict[str, Any]:
        """返回指定时间窗口的调用摘要统计."""
        since = datetime.utcnow() - timedelta(hours=hours)

        q = select(ModelCallEvent).where(ModelCallEvent.created_at >= since)
        if agent_role_key:
            q = q.where(ModelCallEvent.agent_role_key == agent_role_key)
        if provider_id:
            q = q.where(ModelCallEvent.provider_id == provider_id)

        events = (await db.execute(q)).scalars().all()

        total = len(events)
        success = sum(1 for e in events if e.status in ("success", "fallback_success"))
        failed = sum(1 for e in events if e.status in ("failed", "fallback_failed"))
        fallback = sum(1 for e in events if e.status == "fallback_success")

        total_cost = sum(e.cost_usd for e in events)
        total_input_tokens = sum(e.input_tokens for e in events)
        total_output_tokens = sum(e.output_tokens for e in events)

        latencies = [e.latency_ms for e in events if e.latency_ms is not None]
        avg_latency = int(sum(latencies) / len(latencies)) if latencies else 0
        p95_latency = int(sorted(latencies)[int(len(latencies) * 0.95)]) if len(latencies) >= 20 else None

        # 按 agent_role_key 分组
        role_stats: dict[str, dict] = {}
        for e in events:
            rk = e.agent_role_key or "unknown"
            if rk not in role_stats:
                role_stats[rk] = {"total": 0, "success": 0, "failed": 0, "fallback": 0,
                                  "cost_usd": 0.0, "input_tokens": 0, "output_tokens": 0}
            s = role_stats[rk]
            s["total"] += 1
            if e.status in ("success", "fallback_success"):
                s["success"] += 1
            elif e.status in ("failed", "fallback_failed"):
                s["failed"] += 1
            if e.status == "fallback_success":
                s["fallback"] += 1
            s["cost_usd"] += e.cost_usd
            s["input_tokens"] += e.input_tokens
            s["output_tokens"] += e.output_tokens

        # 按 failure_type 分组
        failure_counts: dict[str, int] = {}
        for e in events:
            if e.failure_type:
                failure_counts[e.failure_type] = failure_counts.get(e.failure_type, 0) + 1

        # 按 provider_id 分组
        provider_stats: dict[int, dict] = {}
        for e in events:
            if e.provider_id:
                if e.provider_id not in provider_stats:
                    provider_stats[e.provider_id] = {
                        "total": 0, "success": 0, "failed": 0, "cost_usd": 0.0
                    }
                ps = provider_stats[e.provider_id]
                ps["total"] += 1
                if e.status in ("success", "fallback_success"):
                    ps["success"] += 1
                elif e.status in ("failed", "fallback_failed"):
                    ps["failed"] += 1
                ps["cost_usd"] += e.cost_usd

        return {
            "window_hours": hours,
            "since": since.isoformat(),
            "total_calls": total,
            "success_calls": success,
            "failed_calls": failed,
            "fallback_calls": fallback,
            "success_rate": round(success / total, 4) if total else 0.0,
            "fallback_rate": round(fallback / total, 4) if total else 0.0,
            "total_cost_usd": round(total_cost, 6),
            "total_input_tokens": total_input_tokens,
            "total_output_tokens": total_output_tokens,
            "avg_latency_ms": avg_latency,
            "p95_latency_ms": p95_latency,
            "by_role": role_stats,
            "by_failure_type": failure_counts,
            "by_provider": {str(k): v for k, v in provider_stats.items()},
        }

    async def get_recent_events(
        self,
        db: AsyncSession,
        *,
        limit: int = 50,
        agent_role_key: str | None = None,
        provider_id: int | None = None,
        status: str | None = None,
    ) -> list[dict]:
        """返回最近的调用事件列表."""
        q = select(ModelCallEvent).order_by(desc(ModelCallEvent.id)).limit(limit)
        if agent_role_key:
            q = q.where(ModelCallEvent.agent_role_key == agent_role_key)
        if provider_id:
            q = q.where(ModelCallEvent.provider_id == provider_id)
        if status:
            q = q.where(ModelCallEvent.status == status)

        events = (await db.execute(q)).scalars().all()
        return [
            {
                "id": e.id,
                "provider_id": e.provider_id,
                "model_name": e.model_name,
                "agent_role_key": e.agent_role_key,
                "project_id": e.project_id,
                "task_id": e.task_id,
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
                "created_at": e.created_at.isoformat() if e.created_at else None,
            }
            for e in events
        ]

    async def get_provider_stats(
        self,
        db: AsyncSession,
        *,
        hours: int = 24,
    ) -> list[dict]:
        """返回各 Provider 的运行统计 + 健康分."""
        since = datetime.utcnow() - timedelta(hours=hours)

        # 聚合 model_call_events
        events = (await db.execute(
            select(ModelCallEvent).where(ModelCallEvent.created_at >= since)
        )).scalars().all()

        provider_data: dict[int, dict] = {}
        for e in events:
            pid = e.provider_id
            if not pid:
                continue
            if pid not in provider_data:
                provider_data[pid] = {
                    "total": 0, "success": 0, "failed": 0, "fallback": 0,
                    "cost_usd": 0.0, "latencies": [],
                }
            pd = provider_data[pid]
            pd["total"] += 1
            if e.status in ("success", "fallback_success"):
                pd["success"] += 1
            elif e.status in ("failed", "fallback_failed"):
                pd["failed"] += 1
            if e.status == "fallback_success":
                pd["fallback"] += 1
            pd["cost_usd"] += e.cost_usd
            if e.latency_ms:
                pd["latencies"].append(e.latency_ms)

        # 加载 Provider 基本信息
        providers = (await db.execute(select(ModelProvider))).scalars().all()
        result = []
        for p in providers:
            pd = provider_data.get(p.id, {})
            total = pd.get("total", 0)
            success = pd.get("success", 0)
            lats = pd.get("latencies", [])
            result.append({
                "provider_id": p.id,
                "provider_name": p.name,
                "enabled": p.enabled,
                "circuit_state": p.circuit_state,
                "health_score": p.health_score,
                "last_health_status": p.last_health_status,
                "last_health_at": p.last_health_at.isoformat() if p.last_health_at else None,
                "window_hours": hours,
                "total_calls": total,
                "success_calls": success,
                "failed_calls": pd.get("failed", 0),
                "fallback_calls": pd.get("fallback", 0),
                "success_rate": round(success / total, 4) if total else None,
                "total_cost_usd": round(pd.get("cost_usd", 0.0), 6),
                "avg_latency_ms": int(sum(lats) / len(lats)) if lats else None,
            })

        return sorted(result, key=lambda x: x["total_calls"], reverse=True)


_recorder_singleton: AgentRunRecorder | None = None


def get_agent_run_recorder() -> AgentRunRecorder:
    global _recorder_singleton
    if _recorder_singleton is None:
        _recorder_singleton = AgentRunRecorder()
    return _recorder_singleton
