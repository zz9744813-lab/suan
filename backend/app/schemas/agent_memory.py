"""P10: Agent 分层记忆池 — Pydantic Schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


# ============================================================
# Memory Link
# ============================================================

class MemoryLinkCreate(BaseModel):
    target_memory_id: int
    relation_type: str  # supports / conflicts_with / derived_from / ...
    description: str | None = None
    confidence: float = 0.75


class MemoryLinkRead(BaseModel):
    id: int
    source_memory_id: int
    target_memory_id: int
    relation_type: str
    description: str | None
    confidence: float
    created_by_agent_role: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


# ============================================================
# Memory Audit Log
# ============================================================

class MemoryAuditLogRead(BaseModel):
    id: int
    memory_id: int
    project_id: int
    action: str
    before_json: dict[str, Any] | None
    after_json: dict[str, Any] | None
    actor_type: str
    actor_role: str | None
    reason: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


# ============================================================
# Memory Access Log
# ============================================================

class MemoryAccessLogRead(BaseModel):
    id: int
    memory_id: int
    project_id: int
    agent_role: str
    task_id: int | None
    chapter_id: int | None
    access_reason: str | None
    injected_into_prompt: bool
    prompt_section: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


# ============================================================
# Memory Entry — Create / Update / Read / Detail / List
# ============================================================

class MemoryEntryCreate(BaseModel):
    agent_role: str
    agent_name: str | None = None
    visibility: str = "shared_project"
    memory_layer: str  # temporary / task / long_term / permanent
    memory_type: str  # character / plot / foreshadowing / style / ...
    title: str
    content: str
    summary: str | None = None
    tags: list[str] = Field(default_factory=list)
    chapter_id: int | None = None
    task_id: int | None = None
    discussion_thread_id: int | None = None
    skill_id: int | None = None
    source_type: str = "agent"
    source_id: str | None = None
    source_quote: str | None = None
    source_payload: dict[str, Any] | None = None
    confidence: float = 0.75
    importance: float = 0.5
    ttl_seconds: int | None = None


class MemoryEntryUpdate(BaseModel):
    title: str | None = None
    content: str | None = None
    summary: str | None = None
    tags: list[str] | None = None
    confidence: float | None = None
    importance: float | None = None
    health_score: float | None = None
    visibility: str | None = None
    memory_type: str | None = None


class MemoryEntryRead(BaseModel):
    id: int
    project_id: int
    agent_role: str
    agent_name: str | None
    visibility: str
    memory_layer: str
    memory_type: str
    title: str
    content: str
    summary: str | None
    tags: list[str]
    chapter_id: int | None
    task_id: int | None
    discussion_thread_id: int | None
    skill_id: int | None
    source_type: str
    source_id: str | None
    source_quote: str | None
    confidence: float
    importance: float
    health_score: float
    usage_count: int
    last_used_at: datetime | None
    ttl_seconds: int | None
    expires_at: datetime | None
    archived_at: datetime | None
    is_locked: bool
    is_user_pinned: bool
    is_conflicted: bool
    is_duplicate_candidate: bool
    content_fingerprint: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class MemoryEntryListItem(BaseModel):
    """记忆列表项 — 轻量, 不含完整 content."""
    id: int
    agent_role: str
    visibility: str
    memory_layer: str
    memory_type: str
    title: str
    content_preview: str  # content 前 120 字符
    tags: list[str]
    confidence: float
    importance: float
    health_score: float
    usage_count: int
    last_used_at: datetime | None
    is_locked: bool
    is_conflicted: bool
    is_duplicate_candidate: bool
    expires_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class MemoryEntryDetail(BaseModel):
    """记忆详情 — 包含 links, audit_logs, access_logs."""
    id: int
    project_id: int
    agent_role: str
    agent_name: str | None
    visibility: str
    memory_layer: str
    memory_type: str
    title: str
    content: str
    summary: str | None
    tags: list[str]
    chapter_id: int | None
    task_id: int | None
    discussion_thread_id: int | None
    skill_id: int | None
    source_type: str
    source_id: str | None
    source_quote: str | None
    source_payload: dict[str, Any] | None = None
    confidence: float
    importance: float
    health_score: float
    usage_count: int
    last_used_at: datetime | None
    ttl_seconds: int | None
    expires_at: datetime | None
    archived_at: datetime | None
    deleted_at: datetime | None = None
    is_locked: bool
    is_user_pinned: bool
    is_conflicted: bool
    is_duplicate_candidate: bool
    content_fingerprint: str | None
    created_at: datetime
    updated_at: datetime
    # 关联数据
    links: list[MemoryLinkRead] = Field(default_factory=list)
    audit_logs: list[MemoryAuditLogRead] = Field(default_factory=list)
    recent_access_logs: list[MemoryAccessLogRead] = Field(default_factory=list)

    model_config = {"from_attributes": True}


# ============================================================
# Consolidation Job
# ============================================================

class ConsolidationJobCreate(BaseModel):
    agent_role: str | None = None
    job_types: list[str] = Field(
        default_factory=lambda: ["dedupe", "promote", "expire", "conflict_check"],
    )


class ConsolidationJobRead(BaseModel):
    id: int
    project_id: int
    agent_role: str | None
    job_type: str
    status: str
    input_json: dict[str, Any] | None
    result_json: dict[str, Any] | None
    error_message: str | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None

    model_config = {"from_attributes": True}


# ============================================================
# Change Request (永久记忆修改)
# ============================================================

class ChangeRequestCreate(BaseModel):
    memory_id: int
    request_type: str  # update / delete / demote / unlock
    reason: str
    proposed_content: str | None = None
    proposed_patch: dict[str, Any] | None = None


class ChangeRequestReview(BaseModel):
    status: str  # approved / rejected
    review_note: str | None = None


class ChangeRequestRead(BaseModel):
    id: int
    project_id: int
    memory_id: int
    request_type: str
    requested_by_agent_role: str | None
    reason: str
    proposed_content: str | None
    proposed_patch_json: dict[str, Any] | None
    status: str
    reviewed_by: str | None
    reviewed_at: datetime | None
    review_note: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


# ============================================================
# Actions: Promote / Demote / Archive / Merge / MarkConflict
# ============================================================

class MemoryPromoteRequest(BaseModel):
    target_layer: str  # task / long_term / permanent
    reason: str
    actor_type: str = "user"  # agent / user / system


class MemoryDemoteRequest(BaseModel):
    target_layer: str  # temporary / task
    reason: str
    actor_type: str = "user"


class MemoryArchiveRequest(BaseModel):
    reason: str


class MemoryMergeRequest(BaseModel):
    source_ids: list[int]
    merged_title: str
    merged_content: str
    target_layer: str
    reason: str


class MemoryMarkConflictRequest(BaseModel):
    conflict_with_memory_id: int
    reason: str


# ============================================================
# Stats / Agent / Graph
# ============================================================

class MemoryProjectStats(BaseModel):
    project_id: int
    total: int = 0
    by_layer: dict[str, int] = Field(default_factory=dict)
    by_agent: dict[str, int] = Field(default_factory=dict)
    conflict_count: int = 0
    duplicate_candidate_count: int = 0
    health_score: float = 1.0


class AgentMemoryStats(BaseModel):
    agent_role: str
    agent_name: str | None = None
    memory_count: int = 0
    temporary_count: int = 0
    task_count: int = 0
    long_term_count: int = 0
    permanent_count: int = 0
    conflict_count: int = 0
    health_score: float = 1.0
    last_written_at: datetime | None = None
    has_pending_audit: bool = False


class MemoryGraphData(BaseModel):
    nodes: list[dict[str, Any]] = Field(default_factory=list)
    edges: list[dict[str, Any]] = Field(default_factory=list)


# ============================================================
# List Response
# ============================================================

class MemoryEntryListResponse(BaseModel):
    items: list[MemoryEntryListItem]
    total: int


class AgentMemoryListResponse(BaseModel):
    items: list[AgentMemoryStats]
