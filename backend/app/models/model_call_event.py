"""P0-Model-Failover: 模型调用事件表.

每次模型调用记录一条, 用于:
  - UI 展示为什么选这个 API
  - 健康评分从真实调用事件聚合
  - 24h 运行出错时定位哪个 Provider/Model/Agent 挂了
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Float, ForeignKey, Integer, String, Text
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

    created_at: Mapped[datetime] = mapped_column(default=_utcnow, index=True)
