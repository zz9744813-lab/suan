"""Discussion Room — 多 Agent 圆桌讨论的会话与发言表。

每个 DiscussionSession 是一次圆桌讨论, DiscussionTurn 是每位参与者的
一次发言。Turn 顺序按 created_at 排列 (也存了 turn_no 冗余以便排版)。
最后一条是 chief_synthesis(由主 Agent 综合)。

不在 chief_agent_sessions / chief_agent_messages 里塞, 因为:
  - chief_agent 是 1:1 对话, schema 不一样
  - Discussion 会有 N+1 条 turn (N 个参与者 + 1 个综合)
  - 需要存 parsed JSON (key_points, concerns), 不是单一 content 字符串
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def _utcnow() -> datetime:
    return datetime.utcnow()


class DiscussionSession(Base):
    __tablename__ = "discussion_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int | None] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"), default=None, index=True
    )
    topic: Mapped[str] = mapped_column(String(500))
    participants: Mapped[list[str]] = mapped_column(JSON, default=list)
    # 状态: running / succeeded / failed / partial
    # partial = 部分参与者成功, 部分失败 (用户仍可看成功的)
    status: Mapped[str] = mapped_column(String(20), default="running")
    error: Mapped[str | None] = mapped_column(Text, default=None)
    total_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    total_input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow, index=True)


class DiscussionTurn(Base):
    __tablename__ = "discussion_turns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("discussion_sessions.id", ondelete="CASCADE"), index=True
    )
    # 顺序: 1..N 是参与者, N+1 是 chief_synthesis
    turn_no: Mapped[int] = mapped_column(Integer)
    # agent_name: PlannerAgent / DrafterAgent / CriticAgent / ContinuityAgent
    #             / MemoryUpdateAgent / ChiefAgent
    agent_name: Mapped[str] = mapped_column(String(60))
    role_label: Mapped[str] = mapped_column(String(60), default="")  # "策划" / "主笔" / ...
    kind: Mapped[str] = mapped_column(String(20))  # participant / synthesis
    content: Mapped[str] = mapped_column(Text, default="")
    parsed: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=None)
    error: Mapped[str | None] = mapped_column(Text, default=None)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
