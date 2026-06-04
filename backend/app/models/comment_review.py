"""P6: 评论区驱动的模拟读者 Agent 评审系统 — 5 张新表.

跟现有数据模型的关系 (P6 spec §3):
  - AgentRole / AgentModelBinding / AgentPromptBinding (P4)
    → 5 个读者 Agent + 1 个主 Agent 评论接入官
    → 各自独立绑定 provider/model/prompt
  - DiscussionSession / DiscussionTurn (P2)
    → 评论组触发讨论时复用, 不另建讨论表
  - ReviewSettings 1:1 project, 跟 WorkerPolicy 平级
  - ReaderAgentProfile 1:1 agent_role, 存读者权重 + 采纳统计
  - ReviewComment 是"评论区主表", 同时容纳:
      - 用户评论 (author_type='user')
      - 读者 Agent 评论 (author_type='reader_agent')
      - 主 Agent 回复 (author_type='chief_agent', parent_id != null)
      - 系统消息 (author_type='system', e.g. 接入成功/已合并)
  - ReviewCommentGroup 是主 Agent 合并相似评论后的"问题包"
  - ReaderReviewRun 是每次自动读者评审任务的元数据

注意:
  - ReviewComment 默认 expires_at = now + 7 天, 过期硬删
  - 采纳统计必须先写入 ReaderAgentProfile 再删原评论
  - ReviewCommentGroup.decision 永久保存, 不依赖原评论存在
  - P0 这一轮只建表 + seed, 后端 API / worker 集成在 P1-P4 阶段
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def _utcnow() -> datetime:
    return datetime.utcnow()


# ============================================================
# ReaderAgentProfile (P6 §3.1) — 读者 Agent 的长期档案
# ============================================================
class ReaderAgentProfile(Base):
    """每个读者 Agent 一行, 保存权重 + 采纳统计 + 启用状态.

    weight 是浮动值, 范围 [0.5, 2.5] (P6 §4.5):
      - 被采纳一次 → +0.08
      - 被驳回一次 → -0.03
      - 用户评论永远 1.0, 不进浮动 (用户是 ground truth)

    next 评论合并时按 weight 降序, 高权重读者评论排序靠前, 影响合并方向。
    """

    __tablename__ = "reader_agent_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    agent_role_id: Mapped[int] = mapped_column(
        ForeignKey("agent_roles.id", ondelete="CASCADE"),
        unique=True, index=True,
    )
    # 跟 AgentRole.key 一致 (reader_hook / reader_emotion / ...), 冗余存储
    # 便于评论流 / 矩阵直接查
    reader_key: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(120))
    # 评审维度 (节奏 / 情绪 / 逻辑 / 商业 / 毒点)
    dimension: Mapped[str] = mapped_column(String(80))

    weight: Mapped[float] = mapped_column(Float, default=1.0)
    adopted_count: Mapped[int] = mapped_column(Integer, default=0)
    rejected_count: Mapped[int] = mapped_column(Integer, default=0)
    generated_comment_count: Mapped[int] = mapped_column(Integer, default=0)

    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_used_at: Mapped[datetime | None] = mapped_column(default=None)

    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        default=_utcnow, onupdate=_utcnow,
    )


# ============================================================
# ReviewComment (P6 §3.2) — 评论区主表
# ============================================================
class ReviewComment(Base):
    """评论区主表, 同时容纳 4 种 author_type:
      - user: 真实用户发表的评论
      - reader_agent: 5 个读者 Agent 自动生成的评审
      - chief_agent: 主 Agent (chief_comment_moderator) 的回复/接入
      - system: 系统消息 (e.g. "已合并", "已转讨论", "7 天后将清理")

    status 状态机 (P6 §8.4):
      new → replied → grouped → discussing → accepted / rejected / ignored → done

    关键约束:
      - parent_id 实现评论树 (主 Agent 回复挂在被回复评论下)
      - related_group_id 关联到 ReviewCommentGroup
      - related_discussion_id 关联到 DiscussionSession (转讨论后写入)
      - expires_at 普通评论 7 天后清理, 采纳统计已写入 ReaderAgentProfile
    """

    __tablename__ = "review_comments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True,
    )
    chapter_id: Mapped[int | None] = mapped_column(
        ForeignKey("chapters.id", ondelete="CASCADE"), default=None, index=True,
    )
    chapter_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("chapter_versions.id", ondelete="SET NULL"),
        default=None, index=True,
    )

    # 父评论 (主 Agent 回复时填), 实现评论树
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("review_comments.id", ondelete="CASCADE"),
        default=None, index=True,
    )

    # 评价对象类型: project / chapter / version / book
    target_type: Mapped[str] = mapped_column(String(30), default="chapter")

    # author_type: user / reader_agent / chief_agent / system
    author_type: Mapped[str] = mapped_column(String(30), index=True)

    author_label: Mapped[str] = mapped_column(String(120))
    agent_role_id: Mapped[int | None] = mapped_column(
        ForeignKey("agent_roles.id", ondelete="SET NULL"),
        default=None, index=True,
    )

    content: Mapped[str] = mapped_column(Text)
    # 证据定位 (读者 Agent 输出, 用户评论为 null)
    evidence: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSON, default=None,
    )
    # 评分 (读者 Agent 输出: {score: 0-100, dimensions: {...}})
    rating: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=None)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)

    # 创建时的读者权重, 用于事后回溯"当时这个读者权重多少"
    weight_at_created: Mapped[float] = mapped_column(Float, default=1.0)

    # 状态机: new / replied / grouped / discussing / accepted / rejected /
    #         ignored / done
    status: Mapped[str] = mapped_column(
        String(30), default="new", index=True,
    )

    # 优先级 0-100, 50 是默认值, 高优评论先接入
    priority: Mapped[int] = mapped_column(Integer, default=50)

    # 关联到评论组 (合并后写入)
    related_group_id: Mapped[int | None] = mapped_column(
        ForeignKey("review_comment_groups.id", ondelete="SET NULL"),
        default=None, index=True,
    )
    # 关联到讨论 (转讨论后写入)
    related_discussion_id: Mapped[int | None] = mapped_column(
        ForeignKey("discussion_sessions.id", ondelete="SET NULL"),
        default=None, index=True,
    )

    # 过期时间, 7 天后硬删 (系统消息可设 None 永久保留)
    expires_at: Mapped[datetime | None] = mapped_column(default=None, index=True)

    created_at: Mapped[datetime] = mapped_column(
        default=_utcnow, index=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        default=_utcnow, onupdate=_utcnow,
    )


# ============================================================
# ReviewCommentGroup (P6 §3.3) — 主 Agent 合并后的"问题包"
# ============================================================
class ReviewCommentGroup(Base):
    """主 Agent 把多条相似评论合并成一个"问题包", 然后决定:
      - severity=low/medium → 已读 / 忽略
      - severity=high/blocker → 创建 DiscussionSession

    decision JSON 字段保存讨论后裁决:
      {
        "decision": "no_change | light_fix | local_rewrite | full_rewrite",
        "accepted_comment_ids": [...],
        "rejected_comment_ids": [...],
        "rewrite_instruction": "...",
        "validation_plan": "..."
      }

    decision 是永久记录, 即便原 ReviewComment 已被 7 天清理, decision
    依然能反查当时讨论结果。
    """

    __tablename__ = "review_comment_groups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True,
    )
    chapter_id: Mapped[int | None] = mapped_column(
        ForeignKey("chapters.id", ondelete="CASCADE"), default=None, index=True,
    )
    chapter_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("chapter_versions.id", ondelete="SET NULL"),
        default=None, index=True,
    )

    title: Mapped[str] = mapped_column(String(200))
    summary: Mapped[str] = mapped_column(Text)
    comment_ids: Mapped[list[int]] = mapped_column(JSON, default=list)

    # low / medium / high / blocker
    severity: Mapped[str] = mapped_column(String(20), default="medium")

    # new / discussing / decided / rewrite_queued / done / ignored
    status: Mapped[str] = mapped_column(
        String(30), default="new", index=True,
    )

    # 讨论 session (触发讨论后写入)
    discussion_session_id: Mapped[int | None] = mapped_column(
        ForeignKey("discussion_sessions.id", ondelete="SET NULL"),
        default=None, index=True,
    )
    # 裁决 JSON, 见类注释
    decision: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=None)

    created_at: Mapped[datetime] = mapped_column(
        default=_utcnow, index=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        default=_utcnow, onupdate=_utcnow,
    )


# ============================================================
# ReaderReviewRun (P6 §3.4) — 每次自动读者评审任务
# ============================================================
class ReaderReviewRun(Base):
    """一次"5 个读者 Agent 评审某章"的元数据.

    trigger:
      - chapter_completed: 章节流水线完成后自动触发
      - rewrite_completed: 返工完成后复评
      - manual_test: 手动测试 (POST /api/reviews/runs)
      - scheduled: 定时触发 (未来扩展)

    status:
      - pending: 入队
      - running: worker 正在跑
      - succeeded: 5 个读者都成功
      - failed: 全部失败
      - partial: 部分读者成功, 部分失败 (允许继续 triage)
    """

    __tablename__ = "reader_review_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True,
    )
    chapter_id: Mapped[int] = mapped_column(
        ForeignKey("chapters.id", ondelete="CASCADE"), index=True,
    )
    chapter_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("chapter_versions.id", ondelete="SET NULL"),
        default=None, index=True,
    )

    trigger: Mapped[str] = mapped_column(
        String(40), default="chapter_completed",
    )

    status: Mapped[str] = mapped_column(
        String(30), default="pending", index=True,
    )

    # 实际跑过的读者 key 列表
    reader_agent_keys: Mapped[list[str]] = mapped_column(JSON, default=list)
    # 生成的评论 ID 列表
    generated_comment_ids: Mapped[list[int]] = mapped_column(JSON, default=list)

    total_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    total_input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_output_tokens: Mapped[int] = mapped_column(Integer, default=0)

    error: Mapped[str | None] = mapped_column(Text, default=None)

    started_at: Mapped[datetime | None] = mapped_column(default=None)
    finished_at: Mapped[datetime | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(
        default=_utcnow, index=True,
    )


# ============================================================
# ReviewSettings (P6 §3.5) — 项目级评论设置
# ============================================================
class ReviewSettings(Base):
    """项目级设置, 1:1 with Project.

    控制自动化的开关 + 7 天清理 + 评论上限。
    每个项目一行, 缺省值在 seed 时填充。
    """

    __tablename__ = "review_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        unique=True, index=True,
    )

    # 章节完成后是否自动触发 5 个读者 Agent 评审
    auto_reader_review: Mapped[bool] = mapped_column(Boolean, default=True)
    # 用户/读者发评论后是否自动触发主 Agent 接入
    auto_chief_triage: Mapped[bool] = mapped_column(Boolean, default=True)
    # 评论组严重度达到阈值时是否自动创建讨论
    auto_discussion: Mapped[bool] = mapped_column(Boolean, default=True)

    # 普通评论保留天数 (P6 §1.3 强制 7 天)
    retention_days: Mapped[int] = mapped_column(Integer, default=7)

    # 评论上限
    max_comments_per_chapter: Mapped[int] = mapped_column(Integer, default=50)
    # 每次 reader_review 最多生成多少条读者评论
    max_reader_comments_per_run: Mapped[int] = mapped_column(Integer, default=5)

    # 严重度阈值: low / medium / high / blocker
    # 评论组严重度 >= 此值时自动创建讨论
    min_severity_for_discussion: Mapped[str] = mapped_column(
        String(20), default="medium",
    )

    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        default=_utcnow, onupdate=_utcnow,
    )


__all__ = [
    "ReaderAgentProfile",
    "ReviewComment",
    "ReviewCommentGroup",
    "ReaderReviewRun",
    "ReviewSettings",
]
