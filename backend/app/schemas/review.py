"""P6 §6: 评论/评论组/读者评审 — Pydantic schemas.

P1 阶段: 只做 API 端点 + 数据库读写, 不调 LLM, 不做自动 triage.
P2 (AgentRoleRunner) / P3 (Triage + DiscussionBridge) / P4 (Worker) 在
后续阶段补 LLM 调用.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


# ============================================================
# ReviewComment — 评论
# ============================================================
# author_type: 4 种评论来源, 跟 P6 spec §3.2 一致
AuthorType = Literal["user", "reader_agent", "chief_agent", "system"]
CommentStatus = Literal[
    "new", "replied", "grouped", "discussing",
    "accepted", "rejected", "ignored", "done",
]
CommentSeverity = Literal["low", "medium", "high", "blocker"]
TargetType = Literal["project", "chapter", "version", "book"]


class ReviewCommentCreate(BaseModel):
    """用户/系统发评论. author_type 必须显式指定:
      - user: 真实用户发评论
      - reader_agent: 5 个读者 Agent (P2 阶段调 LLM 后由 service 写)
      - chief_agent: 主 Agent 回复 (P3 阶段)
      - system: 系统消息 (e.g. "已合并", "已转讨论")"""
    project_id: int = Field(..., ge=1)
    chapter_id: int | None = None
    chapter_version_id: int | None = None
    parent_id: int | None = None  # 父评论 (chief_agent 回复)
    target_type: TargetType = "chapter"
    author_type: AuthorType
    author_label: str = Field(..., min_length=1, max_length=120)
    agent_role_id: int | None = None  # reader_agent / chief_agent 时填
    content: str = Field(..., min_length=1)
    evidence: list[dict[str, Any]] | None = None
    rating: dict[str, Any] | None = None
    tags: list[str] = Field(default_factory=list)
    weight_at_created: float = 1.0
    priority: int = Field(50, ge=0, le=100)
    expires_in_days: int | None = None  # None = 用 ReviewSettings.retention_days


class ReviewCommentUpdate(BaseModel):
    """P1 阶段: 只支持改 status / priority / parent_id / tags.
    实际 chief_agent 回复是 PATCH parent_id + 写新评论 (author_type=chief_agent)."""
    status: CommentStatus | None = None
    priority: int | None = Field(None, ge=0, le=100)
    related_group_id: int | None = None
    related_discussion_id: int | None = None
    tags: list[str] | None = None


class ReviewCommentReplyCreate(BaseModel):
    """chief_agent 风格回复 — 单独 endpoint, 自动挂 parent_id."""
    content: str = Field(..., min_length=1, max_length=2000)
    tags: list[str] = Field(default_factory=list)


class ReviewCommentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    chapter_id: int | None
    chapter_version_id: int | None
    parent_id: int | None
    target_type: str
    author_type: str
    author_label: str
    agent_role_id: int | None
    content: str
    evidence: list[dict[str, Any]] | None
    rating: dict[str, Any] | None
    tags: list[str]
    weight_at_created: float
    status: str
    priority: int
    related_group_id: int | None
    related_discussion_id: int | None
    expires_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ReviewCommentWithReplies(ReviewCommentRead):
    """评论 + 父评论下的直接子评论 (chief_agent 回复)."""
    replies: list[ReviewCommentRead] = Field(default_factory=list)


class ReviewCommentListResponse(BaseModel):
    items: list[ReviewCommentRead]
    total: int
    # group_by=chapter 时附带, 其他 group_by 模式未来扩展
    grouped: dict[str, list[ReviewCommentRead]] | None = None


# ============================================================
# ReviewCommentGroup — 评论组
# ============================================================
GroupStatus = Literal[
    "new", "discussing", "decided", "rewrite_queued", "done", "ignored",
]


class ReviewCommentGroupCreate(BaseModel):
    """主 Agent 合并相似评论成"问题包"."""
    project_id: int = Field(..., ge=1)
    chapter_id: int | None = None
    chapter_version_id: int | None = None
    title: str = Field(..., min_length=1, max_length=200)
    summary: str = Field(..., min_length=1)
    comment_ids: list[int] = Field(default_factory=list)
    severity: CommentSeverity = "medium"


class ReviewCommentGroupUpdate(BaseModel):
    title: str | None = None
    summary: str | None = None
    severity: CommentSeverity | None = None
    status: GroupStatus | None = None
    comment_ids: list[int] | None = None


class ReviewCommentGroupRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    chapter_id: int | None
    chapter_version_id: int | None
    title: str
    summary: str
    comment_ids: list[int]
    severity: str
    status: str
    discussion_session_id: int | None
    decision: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime


class ReviewCommentGroupDetail(ReviewCommentGroupRead):
    """评论组 + 关联评论列表 (展开 comment_ids -> ReviewComment)."""
    comments: list[ReviewCommentRead] = Field(default_factory=list)


class GroupDiscussRequest(BaseModel):
    """POST /api/reviews/groups/{id}/discuss — 转讨论.

    P1: 只把 status 改成 'discussing' 并标 discussion_session_id=-1
    (PENDING 标志), 实际 DiscussionSession 创建推到 P3.
    或者: 若 participant_topics 非空, 立刻建一个 DiscussionSession 占位."""
    participant_keys: list[str] = Field(
        default_factory=lambda: ["planner", "critic", "continuity"],
        description="讨论参与者 key (planner/drafter/critic/continuity/memory)",
    )
    note: str | None = None  # 主 Agent 给讨论室的开场白


class GroupDecisionRequest(BaseModel):
    """POST /api/reviews/groups/{id}/decide — 主 Agent 写裁决."""
    decision: Literal["no_change", "light_fix", "local_rewrite", "full_rewrite"]
    accepted_comment_ids: list[int] = Field(default_factory=list)
    rejected_comment_ids: list[int] = Field(default_factory=list)
    rewrite_instruction: str | None = None
    validation_plan: str | None = None


# ============================================================
# ReviewSettings — 项目级设置
# ============================================================
class ReviewSettingsRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    auto_reader_review: bool
    auto_chief_triage: bool
    auto_discussion: bool
    retention_days: int
    max_comments_per_chapter: int
    max_reader_comments_per_run: int
    min_severity_for_discussion: str
    created_at: datetime
    updated_at: datetime


class ReviewSettingsUpdate(BaseModel):
    auto_reader_review: bool | None = None
    auto_chief_triage: bool | None = None
    auto_discussion: bool | None = None
    retention_days: int | None = Field(None, ge=1, le=90)
    max_comments_per_chapter: int | None = Field(None, ge=1, le=500)
    max_reader_comments_per_run: int | None = Field(None, ge=1, le=20)
    min_severity_for_discussion: CommentSeverity | None = None


# ============================================================
# ReaderReviewRun — 5 读者一次评审
# ============================================================
RunTrigger = Literal[
    "chapter_completed", "rewrite_completed", "manual_test", "scheduled",
]
RunStatus = Literal["pending", "running", "succeeded", "failed", "partial"]


class ReaderReviewRunCreate(BaseModel):
    """POST /api/reviews/runs — 内部触发读者评审.

    P1: 只创建 ReaderReviewRun row (status=pending), 实际 5 reader 跑
    推到 P2 (AgentRoleRunner)."""
    project_id: int = Field(..., ge=1)
    chapter_id: int = Field(..., ge=1)
    chapter_version_id: int | None = None
    trigger: RunTrigger = "manual_test"


class ReaderReviewRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    chapter_id: int
    chapter_version_id: int | None
    trigger: str
    status: str
    reader_agent_keys: list[str]
    generated_comment_ids: list[int]
    total_cost_usd: float
    total_input_tokens: int
    total_output_tokens: int
    error: str | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime


class ReaderReviewQuickGenerateResponse(BaseModel):
    run: ReaderReviewRunRead
    comments: list[ReviewCommentRead]


# ============================================================
# ReaderAgentProfile — 读者档案
# ============================================================
class ReaderAgentProfileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    agent_role_id: int
    reader_key: str
    display_name: str
    dimension: str
    weight: float
    adopted_count: int
    rejected_count: int
    generated_comment_count: int
    enabled: bool
    last_used_at: datetime | None
    created_at: datetime
    updated_at: datetime


# ============================================================
# Agent 自动创建评论 (评论自动流 S5-T1)
# ============================================================
class AgentAutoCreateRequest(BaseModel):
    """Agent 任务完成后自动将输出写入评论区.

    - agent_task_id:  触发该评论的 AgentTask.id
    - agent_key:       agent role key (e.g. "critic", "reader_hook")
    - content:         agent 生成的评论内容
    - severity:        严重程度 (agent 输出中解析, 可选)
    - tags:           标签列表 (可选)
    """
    agent_task_id: int = Field(..., ge=1, description="触发该评论的 AgentTask.id")
    project_id: int = Field(..., ge=1)
    chapter_id: int | None = None
    chapter_version_id: int | None = None
    content: str = Field(..., min_length=1, max_length=10000)
    agent_key: str = Field(
        ..., min_length=1, max_length=50,
        description="agent role key, e.g. 'critic', 'reader_hook'",
    )
    severity: CommentSeverity | None = None
    tags: list[str] = Field(default_factory=list)
    priority: int = Field(50, ge=0, le=100)


class AgentAutoCreateResponse(BaseModel):
    """auto-create 的返回: 创建的评论 + 触发的 triage_run_id (如有)."""
    comment: ReviewCommentRead
    triage_enqueued: bool = Field(
        ..., description="是否已入队 comment_triage 任务",
    )
    triage_run_id: int | None = Field(
        None, description="若同步触发了 triage, 返回 run_id",
    )
