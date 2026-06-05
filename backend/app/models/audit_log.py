"""S5-T2 审计日志 — ORM 模型.

记录关键操作:
  - model 切换 (agent 级 / 项目级)
  - prompt 绑定变更 (genre_prompt_map 写入 / 锁定)
  - 评论审核动作 (accept / reject / group / disscuss)
  - agent 任务完成 / 失败
  - ReviewSettings 变更
  - AgentRole 矩阵绑定变更
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AuditLog(Base):
    """全项目统一审计日志表."""

    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)

    # ── 归属 ──────────────────────────────────────────────────
    project_id: Mapped[int | None] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    chapter_id: Mapped[int | None] = mapped_column(
        ForeignKey("chapters.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    agent_task_id: Mapped[int | None] = mapped_column(
        ForeignKey("agent_tasks.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # ── 事件标识 ──────────────────────────────────────────────
    # event_type 枚举 (前端用 category 分组渲染):
    #   model_switch | prompt_binding_change | review_action
    #   agent_task_completed | agent_task_failed | settings_change
    #   agent_role_binding_change | discussion_created
    event_type: Mapped[str] = mapped_column(
        String(60), nullable=False, index=True,
    )

    # actor
    actor_type: Mapped[str] = mapped_column(
        String(20), default="system",
        comment="user | agent | system | worker",
    )
    actor_key: Mapped[str | None] = mapped_column(
        String(80), nullable=True,
        comment="agent key / user name / worker name",
    )

    # ── 内容 ──────────────────────────────────────────────────
    action: Mapped[str] = mapped_column(
        String(255), nullable=False,
        comment="人类可读的动作描述, 如 '切换 planner 模型 → gpt-4o'",
    )
    details: Mapped[dict | None] = mapped_column(
        JSON, nullable=True,
        comment="结构化上下文: before / after / reason 等",
    )

    # ── 时间戳 ────────────────────────────────────────────────
    created_at: Mapped[datetime] = mapped_column(
        default=func.now,
        index=True,
    )

    __table_args__ = (
        Index("idx_audit_project_event", "project_id", "event_type"),
        Index("idx_audit_created", "created_at"),
    )
