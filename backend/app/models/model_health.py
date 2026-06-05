"""P0-Model-Config: ModelHealthSnapshot + ModelRouteEvent 数据模型.

两个表支撑「智能监测调度 + Agent 锁死 + 调用审计」三层能力:
- model_health_snapshots  —— 每个 Provider+Model 的健康画像
- model_route_events      —— 每次路由决策的审计日志
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def _utcnow() -> datetime:
    return datetime.utcnow()


# ============================================================
# ModelHealthSnapshot — Provider × Model 健康画像
# ============================================================
class ModelHealthSnapshot(Base):
    """Per-model health record. Updated by ModelHealthMonitor every 5-30min
    and on every LLM call result.

    One row per (provider_id, model_name) pair.
    """

    __tablename__ = "model_health_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    provider_id: Mapped[int] = mapped_column(
        ForeignKey("model_providers.id", ondelete="CASCADE"), index=True,
    )
    model_name: Mapped[str] = mapped_column(String(200), index=True)

    # ── 状态 ──
    # unknown / healthy / degraded / rate_limited / failing / disabled / mock
    status: Mapped[str] = mapped_column(String(40), default="unknown", index=True)
    health_score: Mapped[float] = mapped_column(Float, default=0.0)

    # ── 成功率/错误率/延迟 ──
    success_rate: Mapped[float] = mapped_column(Float, default=0.0)
    error_rate: Mapped[float] = mapped_column(Float, default=0.0)
    avg_latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    p95_latency_ms: Mapped[int] = mapped_column(Integer, default=0)

    # ── 最近结果 ──
    last_success_at: Mapped[datetime | None] = mapped_column(default=None)
    last_failure_at: Mapped[datetime | None] = mapped_column(default=None)
    last_error_code: Mapped[str | None] = mapped_column(String(80), default=None)
    last_error_message: Mapped[str | None] = mapped_column(Text, default=None)

    # ── 能力标签 ──
    supports_text: Mapped[bool] = mapped_column(Boolean, default=True)
    supports_image: Mapped[bool] = mapped_column(Boolean, default=False)
    supports_video: Mapped[bool] = mapped_column(Boolean, default=False)
    supports_json: Mapped[bool] = mapped_column(Boolean, default=False)
    supports_stream: Mapped[bool] = mapped_column(Boolean, default=False)

    # ── 上下文/输出 ──
    context_window: Mapped[int | None] = mapped_column(Integer, default=None)
    max_output_tokens: Mapped[int | None] = mapped_column(Integer, default=None)

    # ── 价格 ──
    input_price_per_million: Mapped[float | None] = mapped_column(Float, default=None)
    output_price_per_million: Mapped[float | None] = mapped_column(Float, default=None)

    # ── 限流/冷却 ──
    rate_limited_until: Mapped[datetime | None] = mapped_column(default=None)
    cooldown_until: Mapped[datetime | None] = mapped_column(default=None)

    # ── 探针统计 ──
    probe_count: Mapped[int] = mapped_column(Integer, default=0)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=_utcnow, onupdate=_utcnow)


# ============================================================
# ModelRouteEvent — 路由决策审计日志
# ============================================================
class ModelRouteEvent(Base):
    """Audit log for every model routing decision.

    Written by ModelRouter.resolve() on every LLM call.
    """

    __tablename__ = "model_route_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    task_id: Mapped[int | None] = mapped_column(
        ForeignKey("agent_tasks.id", ondelete="SET NULL"), default=None, index=True,
    )
    step_id: Mapped[int | None] = mapped_column(
        ForeignKey("agent_steps.id", ondelete="SET NULL"), default=None, index=True,
    )
    agent_role_key: Mapped[str] = mapped_column(String(120), index=True)

    # ── 绑定模式 ──
    binding_mode: Mapped[str] = mapped_column(String(40))  # auto / manual_with_fallback / locked
    strategy: Mapped[str | None] = mapped_column(String(80), default=None)

    # ── 最终选择 ──
    selected_provider_id: Mapped[int | None] = mapped_column(default=None)
    selected_model_name: Mapped[str | None] = mapped_column(String(200), default=None)

    # ── 尝试过的模型 ──
    attempted_provider_id: Mapped[int | None] = mapped_column(default=None)
    attempted_model_name: Mapped[str | None] = mapped_column(String(200), default=None)

    # ── 路由原因 ──
    # locked_by_user / manual_primary_ok / manual_primary_failed_fallback
    # / auto_quality_first / auto_speed_first / auto_cost_first
    # / rate_limited_skip / health_degraded_skip
    # / mock_blocked_in_production / no_available_model
    route_reason: Mapped[str] = mapped_column(String(120), index=True)

    # ── 锁死标记 ──
    locked: Mapped[bool] = mapped_column(Boolean, default=False)
    fallback_used: Mapped[bool] = mapped_column(Boolean, default=False)
    fallback_reason: Mapped[str | None] = mapped_column(Text, default=None)

    # ── 健康分/延迟 ──
    health_score: Mapped[float | None] = mapped_column(Float, default=None)
    latency_ms: Mapped[int | None] = mapped_column(Integer, default=None)

    # ── 错误 ──
    error_code: Mapped[str | None] = mapped_column(String(80), default=None)
    error_message: Mapped[str | None] = mapped_column(Text, default=None)

    created_at: Mapped[datetime] = mapped_column(default=_utcnow, index=True)
