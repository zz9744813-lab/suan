"""P0-Model-Failover: 模型调用事件表.

每次模型调用记录一条, 用于:
  - UI 展示为什么选这个 API
  - 健康评分从真实调用事件聚合
  - 24h 运行出错时定位哪个 Provider/Model/Agent 挂了
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def _utcnow() -> datetime:
    return datetime.utcnow()


class ModelCallEvent(Base):
    """One model call event — success or failure."""

    __tablename__ = "model_call_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider_id: Mapped[int | None] = mapped_column(
        ForeignKey("model_providers.id", ondelete="SET NULL"), index=True,
    )
    model_name: Mapped[str | None] = mapped_column(String(200), index=True)
    agent_role_key: Mapped[str | None] = mapped_column(String(80), index=True)

    project_id: Mapped[int | None] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"), default=None, index=True,
    )
    task_id: Mapped[int | None] = mapped_column(
        ForeignKey("agent_tasks.id", ondelete="SET NULL"), default=None, index=True,
    )
    agent_step_id: Mapped[int | None] = mapped_column(
        ForeignKey("agent_steps.id", ondelete="SET NULL"), default=None,
    )

    # auto / manual / manual_with_fallback
    selection_mode: Mapped[str | None] = mapped_column(String(30), default=None)
    selection_score: Mapped[float | None] = mapped_column(Float, default=None)
    selection_reason: Mapped[str | None] = mapped_column(Text, default=None)

    # success / failed / fallback_success / fallback_failed
    status: Mapped[str] = mapped_column(String(20), index=True)
    # auth_error / rate_limited / timeout / connection_error / server_error /
    # empty_response / json_parse_failed / model_not_found / budget_exhausted / unknown
    failure_type: Mapped[str | None] = mapped_column(String(60), default=None)
    failure_message: Mapped[str | None] = mapped_column(Text, default=None)

    latency_ms: Mapped[int | None] = mapped_column(Integer, default=None)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)

    # ── 事件分类 (P0-observability-rework) ──
    # request_started / request_succeeded / request_failed / request_timeout /
    # request_cancelled / fallback_triggered / fallback_succeeded / fallback_failed /
    # model_selected / model_health_check / rate_limited / budget_blocked /
    # json_parse_failed / empty_output / quality_gate_failed / cost_recorded /
    # cache_hit / cache_miss
    event_type: Mapped[str | None] = mapped_column(String(50), default=None, index=True)
    # routing / request / quality / cost / health / rate_limit / system
    event_category: Mapped[str | None] = mapped_column(String(50), default=None, index=True)
    # info / success / warning / error / critical
    level: Mapped[str | None] = mapped_column(String(20), default=None, index=True)

    # ── 上下文增强 ──
    chapter_id: Mapped[int | None] = mapped_column(
        ForeignKey("chapters.id", ondelete="SET NULL"), default=None, index=True,
    )
    step_key: Mapped[str | None] = mapped_column(String(50), default=None)
    provider_name: Mapped[str | None] = mapped_column(String(120), default=None)

    # ── Fallback 详情 ──
    fallback_from_provider: Mapped[str | None] = mapped_column(String(120), default=None)
    fallback_from_model: Mapped[str | None] = mapped_column(String(200), default=None)
    fallback_to_provider: Mapped[str | None] = mapped_column(String(120), default=None)
    fallback_to_model: Mapped[str | None] = mapped_column(String(200), default=None)

    # ── 摘要与详情 ──
    summary: Mapped[str | None] = mapped_column(Text, default=None)
    detail_json: Mapped[str | None] = mapped_column(Text, default=None)  # JSON string

    # ── 缓存 ──
    cache_hit: Mapped[bool | None] = mapped_column(Boolean, default=None)

    # ── 请求ID ──
    request_id: Mapped[str | None] = mapped_column(String(120), default=None)

    # ── 错误码 ──
    error_code: Mapped[str | None] = mapped_column(String(80), default=None)

    created_at: Mapped[datetime] = mapped_column(default=_utcnow, index=True)
