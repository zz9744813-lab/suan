"""P9: Discussion Auto-Trace — Agent 自动讨论留痕 + Skill 沉淀

新增 5 张表:
  - discussion_threads: 讨论线程（替代旧的 session 概念，支持状态机和回收）
  - discussion_messages: Agent 发言留痕（替代旧的 turn，支持 evidence/decision_tags/LLM 追踪）
  - discussion_issue_sources: 问题来源证据
  - discussion_skill_drafts: 讨论生成的临时 Skill 草案
  - discussion_recycle_jobs: 回收任务

旧的 discussion_sessions / discussion_turns 保留不动，新表并存。
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import JSON, Boolean, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def _utcnow() -> datetime:
    return datetime.utcnow()


def _default_recycle_at() -> datetime:
    return datetime.utcnow() + timedelta(days=7)


# ---------------------------------------------------------------------------
# DiscussionThread — 讨论线程
# ---------------------------------------------------------------------------
class DiscussionThread(Base):
    __tablename__ = "discussion_threads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    project_id: Mapped[int | None] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"), default=None, index=True
    )
    chapter_id: Mapped[int | None] = mapped_column(
        ForeignKey("chapters.id", ondelete="SET NULL"), default=None, index=True
    )
    task_id: Mapped[int | None] = mapped_column(
        ForeignKey("agent_tasks.id", ondelete="SET NULL"), default=None, index=True
    )

    title: Mapped[str] = mapped_column(String(255))
    summary: Mapped[str | None] = mapped_column(Text, default=None)

    # 问题来源: critic / reader / continuity / planner / drafter / user / system
    source_type: Mapped[str] = mapped_column(String(32), default="system")
    source_agent_role: Mapped[str | None] = mapped_column(String(64), default=None)

    # 问题类型: logic / character / pacing / continuity / foreshadowing / style / commercial_hook / other
    issue_type: Mapped[str] = mapped_column(String(64), default="other")

    # 风险等级: low / medium / high / critical
    risk_level: Mapped[str] = mapped_column(String(32), default="medium")

    # 状态机:
    # pending_discussion / discussing / converged / rewrite_created /
    # skill_draft_created / archived / recycled / ignored / failed
    status: Mapped[str] = mapped_column(String(64), default="pending_discussion", index=True)

    requires_user_review: Mapped[bool] = mapped_column(Boolean, default=False)

    # Chief 结论
    final_decision: Mapped[str | None] = mapped_column(String(64), default=None)  # modify / no_modify / defer / need_more_context
    final_reason: Mapped[str | None] = mapped_column(Text, default=None)
    final_action_json: Mapped[dict | None] = mapped_column(JSON, default=None)

    # 回收
    created_at: Mapped[datetime] = mapped_column(default=_utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(default=_utcnow, onupdate=_utcnow)
    recycle_at: Mapped[datetime] = mapped_column(default=_default_recycle_at)
    recycled_at: Mapped[datetime | None] = mapped_column(default=None)
    archive_payload_json: Mapped[dict | None] = mapped_column(JSON, default=None)

    # 成果绑定
    rewrite_task_id: Mapped[int | None] = mapped_column(
        ForeignKey("agent_tasks.id", ondelete="SET NULL"), default=None
    )
    skill_draft_id: Mapped[int | None] = mapped_column(
        ForeignKey("discussion_skill_drafts.id", ondelete="SET NULL"), default=None
    )

    # 去重指纹
    issue_fingerprint: Mapped[str | None] = mapped_column(String(128), default=None, index=True)


# ---------------------------------------------------------------------------
# DiscussionMessage — Agent 发言留痕
# ---------------------------------------------------------------------------
class DiscussionMessage(Base):
    __tablename__ = "discussion_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    thread_id: Mapped[int] = mapped_column(
        ForeignKey("discussion_threads.id", ondelete="CASCADE"), index=True
    )

    # speaker_type: agent / chief / skill_builder / system
    speaker_type: Mapped[str] = mapped_column(String(32), default="agent")
    speaker_role: Mapped[str] = mapped_column(String(64))  # planner / drafter / critic / continuity / chief / skill_builder
    speaker_name: Mapped[str | None] = mapped_column(String(128), default=None)

    content: Mapped[str] = mapped_column(Text)
    evidence_json: Mapped[dict | None] = mapped_column(JSON, default=None)
    decision_tags_json: Mapped[list | None] = mapped_column(JSON, default=None)

    confidence: Mapped[float | None] = mapped_column(Float, default=None)
    accepted_by_chief: Mapped[bool] = mapped_column(Boolean, default=False)

    # LLM 调用追踪
    provider_role: Mapped[str | None] = mapped_column(String(64), default=None)
    provider_name: Mapped[str | None] = mapped_column(String(128), default=None)
    model_name: Mapped[str | None] = mapped_column(String(128), default=None)
    input_prompt: Mapped[str | None] = mapped_column(Text, default=None)
    raw_output: Mapped[str | None] = mapped_column(Text, default=None)
    parsed_output_json: Mapped[dict | None] = mapped_column(JSON, default=None)
    error_message: Mapped[str | None] = mapped_column(Text, default=None)

    token_in: Mapped[int] = mapped_column(Integer, default=0)
    token_out: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)

    created_at: Mapped[datetime] = mapped_column(default=_utcnow)


# ---------------------------------------------------------------------------
# DiscussionIssueSource — 问题来源证据
# ---------------------------------------------------------------------------
class DiscussionIssueSource(Base):
    __tablename__ = "discussion_issue_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    thread_id: Mapped[int] = mapped_column(
        ForeignKey("discussion_threads.id", ondelete="CASCADE"), index=True
    )

    source_type: Mapped[str] = mapped_column(String(64))  # critic_score / reader_feedback / continuity_check / user_note
    source_id: Mapped[int | None] = mapped_column(Integer, default=None)

    chapter_id: Mapped[int | None] = mapped_column(
        ForeignKey("chapters.id", ondelete="SET NULL"), default=None
    )
    chapter_index: Mapped[int | None] = mapped_column(Integer, default=None)

    quote: Mapped[str | None] = mapped_column(Text, default=None)
    problem_summary: Mapped[str] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(String(32), default="medium")
    payload_json: Mapped[dict | None] = mapped_column(JSON, default=None)

    created_at: Mapped[datetime] = mapped_column(default=_utcnow)


# ---------------------------------------------------------------------------
# DiscussionSkillDraft — 讨论生成的临时 Skill 草案
# ---------------------------------------------------------------------------
class DiscussionSkillDraft(Base):
    __tablename__ = "discussion_skill_drafts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    thread_id: Mapped[int] = mapped_column(
        ForeignKey("discussion_threads.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )

    title: Mapped[str] = mapped_column(String(255))
    skill_type: Mapped[str] = mapped_column(String(64))  # rewrite / character / pacing / continuity / foreshadowing
    status: Mapped[str] = mapped_column(String(64), default="draft")  # draft / solidified / rejected / expired

    trigger_conditions_json: Mapped[list] = mapped_column(JSON, default=list)
    applicable_scenes_json: Mapped[list] = mapped_column(JSON, default=list)
    anti_patterns_json: Mapped[list] = mapped_column(JSON, default=list)
    execution_template: Mapped[str] = mapped_column(Text)
    prompt_snippet: Mapped[str | None] = mapped_column(Text, default=None)

    applicable_agent_roles_json: Mapped[list] = mapped_column(JSON, default=list)
    source_summary: Mapped[str | None] = mapped_column(Text, default=None)
    source_thread_summary: Mapped[str | None] = mapped_column(Text, default=None)

    quality_score: Mapped[float] = mapped_column(Float, default=0.0)
    usage_count: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
    solidified_at: Mapped[datetime | None] = mapped_column(default=None)
    solidified_skill_id: Mapped[int | None] = mapped_column(
        ForeignKey("skills.id", ondelete="SET NULL"), default=None
    )


# ---------------------------------------------------------------------------
# DiscussionRecycleJob — 回收任务
# ---------------------------------------------------------------------------
class DiscussionRecycleJob(Base):
    __tablename__ = "discussion_recycle_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    thread_id: Mapped[int] = mapped_column(
        ForeignKey("discussion_threads.id", ondelete="CASCADE"), index=True
    )

    status: Mapped[str] = mapped_column(String(64), default="scheduled")  # scheduled / running / completed / failed / cancelled
    scheduled_at: Mapped[datetime] = mapped_column(default=_utcnow)
    executed_at: Mapped[datetime | None] = mapped_column(default=None)

    action: Mapped[str] = mapped_column(String(64), default="compress_and_skill")  # compress_and_skill / compress_only / cancel
    result_json: Mapped[dict | None] = mapped_column(JSON, default=None)
    error_message: Mapped[str | None] = mapped_column(Text, default=None)

    created_at: Mapped[datetime] = mapped_column(default=_utcnow)


# ---------------------------------------------------------------------------
# Skill — 正式 Skill 表 (如果不存在则创建)
# ---------------------------------------------------------------------------
class Skill(Base):
    __tablename__ = "skills"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    title: Mapped[str] = mapped_column(String(255))
    skill_type: Mapped[str] = mapped_column(String(64))

    trigger_conditions_json: Mapped[list] = mapped_column(JSON, default=list)
    applicable_scenes_json: Mapped[list] = mapped_column(JSON, default=list)
    anti_patterns_json: Mapped[list] = mapped_column(JSON, default=list)

    execution_template: Mapped[str] = mapped_column(Text)
    prompt_snippet: Mapped[str | None] = mapped_column(Text, default=None)

    applicable_agent_roles_json: Mapped[list] = mapped_column(JSON, default=list)

    source_type: Mapped[str] = mapped_column(String(64), default="discussion")
    source_thread_id: Mapped[int | None] = mapped_column(Integer, default=None)

    quality_score: Mapped[float] = mapped_column(Float, default=0.0)
    usage_count: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=_utcnow, onupdate=_utcnow)
