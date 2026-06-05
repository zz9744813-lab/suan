"""Task / step / event / worker models (spec §14.2)."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def _utcnow() -> datetime:
    return datetime.utcnow()


class AgentTask(Base):
    """A unit of work (write chapter, review, etc.) executed by the worker."""

    __tablename__ = "agent_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # R21 note: project_id is NOT NULL at the DB level (it was added
    # before the bulk-study path needed orphan tasks). For a
    # project-less book, the bulk endpoint lazily creates / reuses a
    # "拆书·公共" scratch project and binds the AgentTask to that.
    # Chapter-pipeline tasks keep using the material's own project_id.
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    chapter_id: Mapped[int | None] = mapped_column(ForeignKey("chapters.id", ondelete="SET NULL"), index=True, default=None)
    task_type: Mapped[str] = mapped_column(String(50), index=True)
    # chapter_pipeline / study / graph / discussion / memory / learning
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    # pending / running / succeeded / failed / cancelled
    priority: Mapped[int] = mapped_column(Integer, default=100)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(Text, default=None)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    max_retries: Mapped[int] = mapped_column(Integer, default=3)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime | None] = mapped_column(default=None)
    finished_at: Mapped[datetime | None] = mapped_column(default=None)
    # 延迟重试: 若该字段非 None 且 > now(), Worker 不拾取该任务
    not_before_at: Mapped[datetime | None] = mapped_column(default=None, index=True)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=_utcnow, onupdate=_utcnow)

    # R28: task center three-layer architecture columns
    parent_task_id: Mapped[int | None] = mapped_column(Integer, nullable=True, default=None)
    visibility: Mapped[str] = mapped_column(String(30), default="user")
    domain: Mapped[str] = mapped_column(String(50), default="writing")
    task_kind: Mapped[str | None] = mapped_column(String(80), nullable=True, default=None)
    material_id: Mapped[int | None] = mapped_column(Integer, nullable=True, default=None)
    run_id: Mapped[int | None] = mapped_column(Integer, nullable=True, default=None)
    stage_key: Mapped[str | None] = mapped_column(String(80), nullable=True, default=None)
    progress_current: Mapped[int] = mapped_column(Integer, default=0)
    progress_total: Mapped[int] = mapped_column(Integer, default=0)
    display_title: Mapped[str | None] = mapped_column(String(240), nullable=True, default=None)
    summary_json: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=None)

    chapter: Mapped["Chapter | None"] = relationship(back_populates="tasks")
    steps: Mapped[list["AgentStep"]] = relationship(back_populates="task", cascade="all, delete-orphan", order_by="AgentStep.id")


class AgentStep(Base):
    """One sub-step inside a task (ContextCompiler, DraftAgent, Critic, etc.).

    Per spec §20.2 every step must save input_prompt, raw_output, parsed_output,
    model_name, provider_name, token counts, cost, duration, error.
    """

    __tablename__ = "agent_steps"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("agent_tasks.id", ondelete="CASCADE"), index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    chapter_id: Mapped[int | None] = mapped_column(ForeignKey("chapters.id", ondelete="SET NULL"), default=None, index=True)
    agent_name: Mapped[str] = mapped_column(String(50), index=True)  # DraftAgent / Critic / ...
    step_name: Mapped[str] = mapped_column(String(80))  # draft / review / rewrite
    status: Mapped[str] = mapped_column(String(20), default="pending")
    input_prompt: Mapped[str | None] = mapped_column(Text, default=None)
    raw_output: Mapped[str | None] = mapped_column(Text, default=None)
    parsed_output: Mapped[dict | None] = mapped_column(JSON, default=None)
    model_name: Mapped[str | None] = mapped_column(String(120), default=None)
    provider_name: Mapped[str | None] = mapped_column(String(120), default=None)
    prompt_template_id: Mapped[int | None] = mapped_column(default=None)
    prompt_version: Mapped[int | None] = mapped_column(default=None)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, default=None)
    started_at: Mapped[datetime | None] = mapped_column(default=None)
    finished_at: Mapped[datetime | None] = mapped_column(default=None)
    is_mock: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)

    task: Mapped["AgentTask"] = relationship(back_populates="steps")


class AgentEvent(Base):
    """Lightweight log row, also mirrored to the SSE event bus."""

    __tablename__ = "agent_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id", ondelete="SET NULL"), default=None, index=True)
    chapter_id: Mapped[int | None] = mapped_column(ForeignKey("chapters.id", ondelete="SET NULL"), default=None, index=True)
    task_id: Mapped[int | None] = mapped_column(ForeignKey("agent_tasks.id", ondelete="SET NULL"), default=None, index=True)
    event_type: Mapped[str] = mapped_column(String(60), index=True)
    level: Mapped[str] = mapped_column(String(10), default="info")  # info / warn / error
    message: Mapped[str] = mapped_column(Text, default="")
    data: Mapped[dict | None] = mapped_column(JSON, default=None)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow, index=True)


class WorkerStatus(Base):
    """Singleton row tracking the 24h worker (spec §5.3)."""

    __tablename__ = "worker_status"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    state: Mapped[str] = mapped_column(String(20), default="idle")  # idle / running / paused / stopped / error
    current_task_id: Mapped[int | None] = mapped_column(default=None)
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(default=None)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)
    today_words: Mapped[int] = mapped_column(Integer, default=0)
    today_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    last_reset_date: Mapped[str | None] = mapped_column(String(10), default=None)  # YYYY-MM-DD
    last_error: Mapped[str | None] = mapped_column(Text, default=None)
    updated_at: Mapped[datetime] = mapped_column(default=_utcnow, onupdate=_utcnow)


class WorkerPolicy(Base):
    """Per-project worker policy (spec §5.3)."""

    __tablename__ = "worker_policies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    daily_word_goal: Mapped[int] = mapped_column(Integer, default=30000)
    daily_budget_usd: Mapped[float] = mapped_column(Float, default=8.0)
    pass_score: Mapped[int] = mapped_column(Integer, default=80)
    max_rewrite_rounds: Mapped[int] = mapped_column(Integer, default=2)
    max_retry_per_task: Mapped[int] = mapped_column(Integer, default=3)
    consecutive_fail_stop: Mapped[int] = mapped_column(Integer, default=3)
    auto_continue: Mapped[bool] = mapped_column(default=True)
    discussion_policy: Mapped[str] = mapped_column(String(20), default="smart")  # off / smart / always
    max_discussion_per_day: Mapped[int] = mapped_column(Integer, default=5)
    max_cost_per_discussion: Mapped[float] = mapped_column(Float, default=0.2)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=_utcnow, onupdate=_utcnow)
