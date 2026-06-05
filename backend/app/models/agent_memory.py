"""P10: Agent 分层记忆池 — 四层生命周期 + 可追溯审计.

6 张新表, 与旧的 memory_characters / memory_v2 共存.

表清单:
  - AgentMemoryEntry            核心记忆表 (四层: temporary/task/long_term/permanent)
  - AgentMemoryLink             记忆关系表 (支持/冲突/替代/伏笔/回收/更新)
  - AgentMemoryAuditLog         记忆审计日志
  - AgentMemoryConsolidationJob 记忆整理任务
  - AgentMemoryAccessLog        记忆调用日志
  - MemoryChangeRequest         永久记忆修改申请表

设计原则:
  - 每条记忆属于某个 Agent 的记忆池 (agent_role)
  - 四层分层: temporary(24h) → task(7~30d) → long_term(长期) → permanent(永久)
  - 永久记忆不能被 Agent 直接修改, 必须走 MemoryChangeRequest
  - 写入时做 fingerprint 去重
  - 所有操作写入审计日志
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def _utcnow() -> datetime:
    return datetime.utcnow()


# ============================================================
# AgentMemoryEntry — 核心记忆表
# ============================================================
class AgentMemoryEntry(Base):
    """Agent 分层记忆核心表.

    每条记忆属于一个项目的某个 Agent, 处于四层之一:
      temporary  — 临时上下文, 默认 24h 过期
      task       — 任务绑定, 随任务结束归档
      long_term  — 跨章节稳定事实
      permanent  — 项目硬设定, 不可自动修改/删除
    """

    __tablename__ = "agent_memory_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True,
    )

    # 写入者 / 所属 Agent
    agent_role: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    agent_name: Mapped[str | None] = mapped_column(String(128), default=None)

    # 可见范围: private_agent / shared_project / global_skill / permanent_project
    visibility: Mapped[str] = mapped_column(
        String(64), nullable=False, default="shared_project", index=True,
    )

    # 四层记忆: temporary / task / long_term / permanent
    memory_layer: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True,
    )

    # 类型: character / plot / foreshadowing / style / critique /
    #       rewrite_constraint / world_rule / task_context / writing_skill /
    #       discussion_result / critic_score / chapter_context
    memory_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, default=None)

    tags_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)

    # 绑定对象
    chapter_id: Mapped[int | None] = mapped_column(
        ForeignKey("chapters.id", ondelete="SET NULL"), default=None, index=True,
    )
    task_id: Mapped[int | None] = mapped_column(
        ForeignKey("agent_tasks.id", ondelete="SET NULL"), default=None, index=True,
    )
    discussion_thread_id: Mapped[int | None] = mapped_column(
        ForeignKey("discussion_threads.id", ondelete="SET NULL"), default=None, index=True,
    )
    skill_id: Mapped[int | None] = mapped_column(
        ForeignKey("skills.id", ondelete="SET NULL"), default=None, index=True,
    )

    # 来源
    source_type: Mapped[str] = mapped_column(
        String(64), nullable=False, default="agent",
    )  # agent / user / system / discussion / chapter
    source_id: Mapped[str | None] = mapped_column(String(128), default=None)
    source_quote: Mapped[str | None] = mapped_column(Text, default=None)
    source_payload_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, default=None,
    )

    # 质量与检索
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.75)
    importance: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    health_score: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)

    usage_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_used_at: Mapped[datetime | None] = mapped_column(default=None)

    # 生命周期
    ttl_seconds: Mapped[int | None] = mapped_column(Integer, default=None)
    expires_at: Mapped[datetime | None] = mapped_column(default=None)
    archived_at: Mapped[datetime | None] = mapped_column(default=None)
    deleted_at: Mapped[datetime | None] = mapped_column(default=None)

    # 控制字段
    is_locked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_user_pinned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_conflicted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_duplicate_candidate: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False,
    )

    # 指纹去重
    content_fingerprint: Mapped[str | None] = mapped_column(
        String(128), default=None, index=True,
    )
    semantic_hash: Mapped[str | None] = mapped_column(
        String(128), default=None, index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        nullable=False, default=_utcnow, index=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False, default=_utcnow, onupdate=_utcnow,
    )

    # ---- Pydantic 友好别名 ----
    # ORM 列名 tags_json → schema 期望 tags
    @property
    def tags(self) -> list[str]:
        return self.tags_json or []

    @tags.setter
    def tags(self, value: list[str]) -> None:
        self.tags_json = value

    # content_preview 用于 MemoryEntryListItem
    @property
    def content_preview(self) -> str:
        if not self.content:
            return ""
        return self.content[:120] + "..." if len(self.content) > 120 else self.content

    # source_payload 用于 schema (ORM 列名 source_payload_json)
    @property
    def source_payload(self) -> dict[str, Any] | None:
        return self.source_payload_json


# ============================================================
# AgentMemoryLink — 记忆关系表
# ============================================================
class AgentMemoryLink(Base):
    """记忆之间的关系.

    relation_type:
      derived_from   — 从某条记忆提炼而来
      supports       — 支持某条设定
      conflicts_with — 与某条记忆冲突
      supersedes     — 替代旧记忆
      duplicates     — 语义重复
      foreshadows    — 作为伏笔
      resolves       — 回收伏笔
      updates        — 更新人物状态
    """

    __tablename__ = "agent_memory_links"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    source_memory_id: Mapped[int] = mapped_column(
        ForeignKey("agent_memory_entries.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    target_memory_id: Mapped[int] = mapped_column(
        ForeignKey("agent_memory_entries.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    relation_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.75)
    created_by_agent_role: Mapped[str | None] = mapped_column(String(64), default=None)
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=_utcnow)


# ============================================================
# AgentMemoryAuditLog — 记忆审计日志
# ============================================================
class AgentMemoryAuditLog(Base):
    """记忆操作审计日志.

    action:
      create / update / promote / demote / merge / conflict_mark /
      archive / delete / lock / unlock / access
    """

    __tablename__ = "agent_memory_audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    memory_id: Mapped[int] = mapped_column(
        ForeignKey("agent_memory_entries.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    action: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    before_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=None)
    after_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=None)
    actor_type: Mapped[str] = mapped_column(
        String(64), nullable=False, default="agent",
    )  # agent / user / system
    actor_role: Mapped[str | None] = mapped_column(String(64), default=None)
    reason: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=_utcnow)


# ============================================================
# AgentMemoryConsolidationJob — 记忆整理任务表
# ============================================================
class AgentMemoryConsolidationJob(Base):
    """记忆整理 (consolidation) 任务.

    job_type:
      dedupe / promote / expire / conflict_check / summarize / rebuild_index
    """

    __tablename__ = "agent_memory_consolidation_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    agent_role: Mapped[str | None] = mapped_column(String(64), default=None, index=True)
    job_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(64), nullable=False, default="pending", index=True,
    )  # pending / running / completed / failed
    input_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=None)
    result_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=None)
    error_message: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=_utcnow)
    started_at: Mapped[datetime | None] = mapped_column(default=None)
    completed_at: Mapped[datetime | None] = mapped_column(default=None)


# ============================================================
# AgentMemoryAccessLog — 记忆调用日志
# ============================================================
class AgentMemoryAccessLog(Base):
    """记录 Agent 调用了哪些记忆, 方便审计 "它为什么这么写"."""

    __tablename__ = "agent_memory_access_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    memory_id: Mapped[int] = mapped_column(
        ForeignKey("agent_memory_entries.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    agent_role: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    task_id: Mapped[int | None] = mapped_column(
        ForeignKey("agent_tasks.id", ondelete="SET NULL"), default=None,
    )
    chapter_id: Mapped[int | None] = mapped_column(
        ForeignKey("chapters.id", ondelete="SET NULL"), default=None,
    )
    access_reason: Mapped[str | None] = mapped_column(Text, default=None)
    injected_into_prompt: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False,
    )
    prompt_section: Mapped[str | None] = mapped_column(String(128), default=None)
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=_utcnow)


# ============================================================
# MemoryChangeRequest — 永久记忆修改申请表
# ============================================================
class MemoryChangeRequest(Base):
    """永久记忆不能直接自动改, 必须走申请.

    request_type: update / delete / demote / unlock
    status: pending / approved / rejected
    """

    __tablename__ = "memory_change_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    memory_id: Mapped[int] = mapped_column(
        ForeignKey("agent_memory_entries.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    request_type: Mapped[str] = mapped_column(String(64), nullable=False)
    requested_by_agent_role: Mapped[str | None] = mapped_column(String(64), default=None)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    proposed_content: Mapped[str | None] = mapped_column(Text, default=None)
    proposed_patch_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=None)
    status: Mapped[str] = mapped_column(
        String(64), nullable=False, default="pending", index=True,
    )
    reviewed_by: Mapped[str | None] = mapped_column(String(128), default=None)
    reviewed_at: Mapped[datetime | None] = mapped_column(default=None)
    review_note: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=_utcnow)
