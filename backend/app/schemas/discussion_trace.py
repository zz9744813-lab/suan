"""P9: Discussion Auto-Trace — Pydantic Schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# IssueSource
# ---------------------------------------------------------------------------
class IssueSourceCreate(BaseModel):
    source_type: str
    source_id: int | None = None
    chapter_id: int | None = None
    chapter_index: int | None = None
    quote: str | None = None
    problem_summary: str
    severity: str = "medium"
    payload_json: dict | None = None


class IssueSourceRead(BaseModel):
    id: int
    thread_id: int
    source_type: str
    source_id: int | None
    chapter_id: int | None
    chapter_index: int | None
    quote: str | None
    problem_summary: str
    severity: str
    payload_json: dict | None
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# DiscussionMessage
# ---------------------------------------------------------------------------
class MessageRead(BaseModel):
    id: int
    thread_id: int
    speaker_type: str
    speaker_role: str
    speaker_name: str | None
    content: str
    evidence_json: dict | None
    decision_tags_json: list | None
    confidence: float | None
    accepted_by_chief: bool
    provider_role: str | None
    provider_name: str | None
    model_name: str | None
    error_message: str | None
    token_in: int
    token_out: int
    cost_usd: float
    created_at: datetime

    model_config = {"from_attributes": True, "protected_namespaces": ()}


# ---------------------------------------------------------------------------
# SkillDraft
# ---------------------------------------------------------------------------
class SkillDraftCreate(BaseModel):
    title: str
    skill_type: str
    trigger_conditions_json: list = Field(default_factory=list)
    applicable_scenes_json: list = Field(default_factory=list)
    anti_patterns_json: list = Field(default_factory=list)
    execution_template: str = ""
    prompt_snippet: str | None = None
    applicable_agent_roles_json: list = Field(default_factory=list)
    source_summary: str | None = None
    source_thread_summary: str | None = None
    quality_score: float = 0.0


class SkillDraftRead(BaseModel):
    id: int
    thread_id: int
    project_id: int
    title: str
    skill_type: str
    status: str
    trigger_conditions_json: list
    applicable_scenes_json: list
    anti_patterns_json: list
    execution_template: str
    prompt_snippet: str | None
    applicable_agent_roles_json: list
    source_summary: str | None
    source_thread_summary: str | None
    quality_score: float
    usage_count: int
    created_at: datetime
    solidified_at: datetime | None
    solidified_skill_id: int | None

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# DiscussionThread — list summary
# ---------------------------------------------------------------------------
class ThreadSummary(BaseModel):
    id: int
    project_id: int | None
    chapter_id: int | None
    title: str
    summary: str | None
    source_type: str
    source_agent_role: str | None
    issue_type: str
    risk_level: str
    status: str
    requires_user_review: bool
    final_decision: str | None
    recycle_at: datetime
    recycled_at: datetime | None
    rewrite_task_id: int | None
    skill_draft_id: int | None
    issue_fingerprint: str | None
    created_at: datetime
    updated_at: datetime
    # computed
    message_count: int = 0
    has_rewrite_task: bool = False
    has_skill_draft: bool = False
    remaining_seconds: float | None = None

    model_config = {"from_attributes": True}


class ThreadListResponse(BaseModel):
    items: list[ThreadSummary]
    total: int


# ---------------------------------------------------------------------------
# DiscussionThread — detail
# ---------------------------------------------------------------------------
class ThreadDetail(BaseModel):
    id: int
    project_id: int | None
    chapter_id: int | None
    task_id: int | None
    title: str
    summary: str | None
    source_type: str
    source_agent_role: str | None
    issue_type: str
    risk_level: str
    status: str
    requires_user_review: bool
    final_decision: str | None
    final_reason: str | None
    final_action_json: dict | None
    recycle_at: datetime
    recycled_at: datetime | None
    archive_payload_json: dict | None
    rewrite_task_id: int | None
    skill_draft_id: int | None
    issue_fingerprint: str | None
    created_at: datetime
    updated_at: datetime
    # relations
    issue_sources: list[IssueSourceRead] = Field(default_factory=list)
    messages: list[MessageRead] = Field(default_factory=list)
    skill_draft: SkillDraftRead | None = None
    # computed
    message_count: int = 0
    has_rewrite_task: bool = False
    has_skill_draft: bool = False
    remaining_seconds: float | None = None

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Create thread (manual user supplement)
# ---------------------------------------------------------------------------
class ThreadCreateRequest(BaseModel):
    project_id: int | None = None
    chapter_id: int | None = None
    title: str = Field(..., min_length=2, max_length=255)
    issue_type: str = "other"
    risk_level: str = "medium"
    user_note: str | None = None


# ---------------------------------------------------------------------------
# Action requests
# ---------------------------------------------------------------------------
class ExtendRecycleRequest(BaseModel):
    days: int = Field(7, ge=1, le=90)
    reason: str | None = None


class SolidifySkillRequest(BaseModel):
    draft_id: int
    force: bool = False


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------
class DiscussionStatsResponse(BaseModel):
    active_count: int = 0
    converged_count: int = 0
    pending_skill_count: int = 0
    recycle_soon_count: int = 0
    total_skill_count: int = 0


# ---------------------------------------------------------------------------
# Skill (formal)
# ---------------------------------------------------------------------------
class SkillRead(BaseModel):
    id: int
    title: str
    skill_type: str
    trigger_conditions_json: list
    applicable_scenes_json: list
    anti_patterns_json: list
    execution_template: str
    prompt_snippet: str | None
    applicable_agent_roles_json: list
    source_type: str
    source_thread_id: int | None
    quality_score: float
    usage_count: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
