"""P0-Model-Failover: 模型运行统计表.

按 provider + model + agent_role_key + 时间窗口聚合, 用于:
  - 自动选择模型时看运行表现
  - UI 展示模型质量趋势
  - Critic/Drafter 质量由评分/返工率推断
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def _utcnow() -> datetime:
    return datetime.utcnow()


class ModelRuntimeStat(Base):
    """Rolling runtime statistics per (provider, model, agent_role, window)."""

    __tablename__ = "model_runtime_stats"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider_id: Mapped[int] = mapped_column(
        ForeignKey("model_providers.id", ondelete="CASCADE"), index=True,
    )
    model_name: Mapped[str] = mapped_column(String(200), index=True)
    agent_role_key: Mapped[str | None] = mapped_column(String(80), index=True)
    # rolling_1h / rolling_24h / all_time
    window: Mapped[str] = mapped_column(String(20), index=True)

    total_calls: Mapped[int] = mapped_column(Integer, default=0)
    success_calls: Mapped[int] = mapped_column(Integer, default=0)
    failed_calls: Mapped[int] = mapped_column(Integer, default=0)

    json_parse_failures: Mapped[int] = mapped_column(Integer, default=0)
    empty_response_failures: Mapped[int] = mapped_column(Integer, default=0)
    timeout_failures: Mapped[int] = mapped_column(Integer, default=0)
    auth_failures: Mapped[int] = mapped_column(Integer, default=0)
    rate_limit_failures: Mapped[int] = mapped_column(Integer, default=0)

    avg_latency_ms: Mapped[int | None] = mapped_column(Integer, default=None)
    p95_latency_ms: Mapped[int | None] = mapped_column(Integer, default=None)

    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)

    # 可由 Critic 分数、人工采纳率、reader_score 回填
    quality_score: Mapped[float | None] = mapped_column(Float, default=None)

    updated_at: Mapped[datetime] = mapped_column(default=_utcnow, onupdate=_utcnow)
