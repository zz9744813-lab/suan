"""NF2 自动填充 Prompt 矩阵的审计和批次模型."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def _utcnow() -> datetime:
    return datetime.utcnow()


class PromptAutoFillBatch(Base):
    """自动填充批次的审计记录.

    每次用户点击「一键自动填充」或系统周期触发时创建一行,
    记录该批次的策略、范围、统计结果。
    """

    __tablename__ = "prompt_auto_fill_batches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    batch_key: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    project_id: Mapped[int | None] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"), default=None, index=True,
    )
    status: Mapped[str] = mapped_column(
        String(30), default="preview", index=True,
    )  # preview / applied / rolled_back / failed
    scope: Mapped[str] = mapped_column(
        String(30), default="all",
    )  # all / empty_only / review_agents / writing_agents
    strategy: Mapped[str] = mapped_column(
        String(40), default="balanced",
    )  # balanced / quality_first / strict_genre

    total_cells: Mapped[int] = mapped_column(Integer, default=0)
    recommended_count: Mapped[int] = mapped_column(Integer, default=0)
    applied_count: Mapped[int] = mapped_column(Integer, default=0)
    skipped_locked_count: Mapped[int] = mapped_column(Integer, default=0)
    missing_template_count: Mapped[int] = mapped_column(Integer, default=0)

    summary_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=None)
    created_by: Mapped[str] = mapped_column(String(40), default="system")
    created_at: Mapped[datetime] = mapped_column(default=_utcnow, index=True)
    applied_at: Mapped[datetime | None] = mapped_column(default=None)
    rolled_back_at: Mapped[datetime | None] = mapped_column(default=None)


class PromptRecommendationLog(Base):
    """单条推荐记录 — 每次 auto_fill 为一个 (agent, genre) 产生一条.

    记录当前模板、推荐模板、评分、置信度、动作、原因、候选列表。
    applied=True 表示该推荐已在 apply 阶段实际写入映射。
    """

    __tablename__ = "prompt_recommendation_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    batch_key: Mapped[str] = mapped_column(String(80), index=True)
    project_id: Mapped[int | None] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"), default=None, index=True,
    )
    agent_role_key: Mapped[str] = mapped_column(String(80), index=True)
    genre: Mapped[str] = mapped_column(String(50), index=True)
    current_template_id: Mapped[int | None] = mapped_column(
        ForeignKey("prompt_templates.id", ondelete="SET NULL"), default=None,
    )
    recommended_template_id: Mapped[int | None] = mapped_column(
        ForeignKey("prompt_templates.id", ondelete="SET NULL"), default=None,
    )
    score: Mapped[float] = mapped_column(Float, default=0.0)
    confidence: Mapped[str] = mapped_column(
        String(20), default="low",
    )  # high / medium / low / missing
    action: Mapped[str] = mapped_column(
        String(30), default="suggest",
    )  # auto_bind / suggest / skip_locked / missing_template / keep_current
    reason_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    candidate_scores_json: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, default=list,
    )
    applied: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow, index=True)


class PromptTemplatePerformance(Base):
    """模板效果统计 — 聚合每个 (template, agent_role, genre) 的使用指标.

    指标来源: AgentStep 执行结果 + 评审反馈。
    供 PromptAutoBinder 评分和历史趋势查询使用。
    """

    __tablename__ = "prompt_template_performance"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    prompt_template_id: Mapped[int] = mapped_column(
        ForeignKey("prompt_templates.id", ondelete="CASCADE"), index=True,
    )
    agent_role_key: Mapped[str | None] = mapped_column(
        String(80), default=None, index=True,
    )
    genre: Mapped[str | None] = mapped_column(
        String(50), default=None, index=True,
    )
    total_uses: Mapped[int] = mapped_column(Integer, default=0)
    success_uses: Mapped[int] = mapped_column(Integer, default=0)
    failed_uses: Mapped[int] = mapped_column(Integer, default=0)
    avg_chapter_score: Mapped[float | None] = mapped_column(Float, default=None)
    avg_reader_score: Mapped[float | None] = mapped_column(Float, default=None)
    avg_critic_score: Mapped[float | None] = mapped_column(Float, default=None)
    rewrite_trigger_rate: Mapped[float] = mapped_column(Float, default=0.0)
    json_parse_failure_rate: Mapped[float] = mapped_column(Float, default=0.0)
    adopted_comment_rate: Mapped[float] = mapped_column(Float, default=0.0)
    last_used_at: Mapped[datetime | None] = mapped_column(default=None)
    updated_at: Mapped[datetime] = mapped_column(default=_utcnow, onupdate=_utcnow)
