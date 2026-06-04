"""P3: RawMemory + StableMemory Pydantic schemas.

Mirrors ``app/models/memory_v2.py`` plus the request/response
shapes the route layer needs. Keep this thin — most of the
detail lives on the ORM model; the Pydantic shape is just for
API contract.

Two things to be aware of:

  1. ``StableMemoryEntity.profile`` is intentionally a free dict
     (extra='allow') — each entity_type (人物/地点/势力/...) can
     carry its own schema without a migration.

  2. ``DiscussionDecision.decision_payload`` shape varies by
     ``topic_type`` (see model comment in memory_v2.py). We don't
     validate the inner shape here; the discussion agent writes
     whatever the topic type requires.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


# ============================================================
# Library (P3 §4) — 书架列表 + 档案馆概览
# ============================================================
class ProjectMemoryShelfItem(BaseModel):
    """One book on the 'project memory shelf'.

    Combines: stable entity counts (per cabinet) + raw pool size
    + pending decisions + last consolidated timestamp. The shelf
    list endpoint joins this all up so the MemoryShelfPage
    doesn't have to fan out.
    """
    model_config = ConfigDict(from_attributes=True)

    project_id: int
    project_name: str
    # Last time the consolidator ran (or null if never).
    last_consolidated_at: datetime | None = None
    # Counts per cabinet. All 7 cabinet values + a 'discussion_pending'
    # marker.
    character_count: int = 0
    location_count: int = 0
    faction_count: int = 0
    item_count: int = 0
    world_rule_count: int = 0
    foreshadow_count: int = 0
    hard_fact_count: int = 0
    # Raw + decision counters — P3 §4 "原始记忆条数 / 待裁决数".
    raw_entry_count: int = 0
    raw_entry_pending: int = 0  # status=raw
    decision_pending: int = 0
    decision_running: int = 0
    # 0..1 — quick 'memory health' score for the shelf. Computed
    # in the route as ``(decided / (decided + pending + failed))``
    # or similar; null if there's no data yet.
    health_score: float | None = None
    # "active" (current) / "archived" (项目归档)
    status: str = "active"


class ProjectMemoryShelfResponse(BaseModel):
    items: list[ProjectMemoryShelfItem]
    # "System maintenance" books — a fixed 3-row strip at the
    # bottom of the shelf (P3 §4: 原始记忆池 / 稳定记忆索引 /
    # 讨论裁决记录). Frontend renders these as their own ShelfRow.
    system_books: list[dict[str, str]] = Field(default_factory=list)


class ProjectMemoryArchiveOverview(BaseModel):
    """The 'second layer' page payload — one project's 7-cabinet
    overview. The right panel of MemoryArchivePage can show
    'health / last update / pending decisions' from this.
    """
    project_id: int
    project_name: str
    health_score: float | None = None
    last_consolidated_at: datetime | None = None
    counts: dict[str, int] = Field(default_factory=dict)
    # Decision summary — the user sees 'pending / running /
    # decided / failed' in the discussion-cabinet header.
    decision_summary: dict[str, int] = Field(default_factory=dict)


# ============================================================
# RawMemoryEntry (P3 §7.1)
# ============================================================
class RawMemoryEntryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    chapter_id: int | None
    chapter_index: int | None
    entry_type: str
    subject: str
    predicate: str | None
    object_value: str | None
    raw_payload: dict[str, Any] = Field(default_factory=dict)
    source_quote: str | None
    source_summary: str | None
    confidence: float
    agent_name: str
    agent_step_id: int | None
    status: str
    processed_at: datetime | None
    merged_into_entity_id: int | None
    created_at: datetime


# ============================================================
# StableMemoryEntity (P3 §7.2)
# ============================================================
class StableMemoryEntityRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    entity_type: str
    canonical_name: str
    aliases: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    profile: dict[str, Any] = Field(default_factory=dict)
    importance: float
    confidence: float
    status: str
    first_chapter_index: int | None
    last_chapter_index: int | None
    created_at: datetime
    updated_at: datetime


class StableMemoryEntityDetail(StableMemoryEntityRead):
    """Adds the 'latest state' + 'evidence' columns for the
    character cabinet (the others reuse StableMemoryEntityRead
    plus their own read shape). The frontend cabinet-render
    helper does the dispatch.
    """
    latest_state: "StableCharacterStateRead | None" = None
    timeline: list["MemoryTimelineEventRead"] = Field(default_factory=list)


# ============================================================
# StableCharacterState (P3 §7.3)
# ============================================================
class StableCharacterStateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    entity_id: int
    current_location: str | None
    current_faction: str | None
    current_goal: str | None
    emotion_state: str | None
    injury_state: str | None
    power_state: str | None
    owned_items: list[str] = Field(default_factory=list)
    abilities: list[str] = Field(default_factory=list)
    secrets: list[str] = Field(default_factory=list)
    last_seen_chapter: int | None
    evidence_entry_ids: list[int] = Field(default_factory=list)
    confidence: float
    updated_at: datetime


# ============================================================
# MemoryTimelineEvent (P3 §7.4)
# ============================================================
class MemoryTimelineEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    entity_id: int | None
    memory_type: str
    chapter_id: int | None
    chapter_index: int | None
    event_title: str
    event_summary: str
    before_state: dict[str, Any] | None
    after_state: dict[str, Any] | None
    source_quote: str | None
    source_entry_id: int | None
    created_by: str
    created_at: datetime


# ============================================================
# DiscussionDecision (P3 §7.5)
# ============================================================
class DiscussionDecisionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    topic_type: str
    topic_title: str
    raw_entry_ids: list[int] = Field(default_factory=list)
    related_entity_ids: list[int] = Field(default_factory=list)
    status: str
    decision_payload: dict[str, Any] | None
    decision: str | None
    reason: str | None
    decided_by_agent: str | None
    discussion_session_id: int | None
    created_at: datetime
    decided_at: datetime | None


# ============================================================
# Request bodies
# ============================================================
class ConsolidateRequest(BaseModel):
    """POST /api/project-memory/{project_id}/consolidate"""
    # The route layer reads the RawMemoryEntry pool with status=raw,
    # pushes them through MemoryConsolidatorAgent, and writes
    # Stable* / DiscussionDecision rows. We let the caller override
    # the confidence threshold (P3 §14 禁 4 默认 0.7).
    min_confidence: float = 0.7
    # Limit how many raw entries to process in this batch. 0 = no
    # cap. The frontend defaults to 50 so the user can see
    # progress in the right panel.
    batch_limit: int = 50
    # Run DiscussionAgent inline after consolidating if any
    # 'needs_discussion' entries emerge. Default true so the user
    # doesn't have to chase two buttons.
    run_discussion_inline: bool = True


class ConsolidateResponse(BaseModel):
    processed: int
    merged: int
    rejected: int
    needs_discussion: int
    decided_inline: int
    decisions_created: list[int] = Field(default_factory=list)
    duration_ms: int
    cost_usd: float = 0.0


class RunDiscussionRequest(BaseModel):
    """POST /api/project-memory/{project_id}/discussion-decisions/{id}/run"""
    # Optional: which participants to invite to the discussion
    # room. Empty = use the default set from the topic type.
    participants: list[str] = Field(default_factory=list)
    max_turns: int = 4


class ApplyDecisionRequest(BaseModel):
    """POST /api/project-memory/{project_id}/discussion-decisions/{id}/apply"""
    # Optional override of the decision payload — the user can
    # tweak the LLM's verdict before applying. Empty = use what
    # the DiscussionAgent wrote.
    decision_payload_override: dict[str, Any] | None = None
    reason_override: str | None = None


class ApplyDecisionResponse(BaseModel):
    decision_id: int
    applied: bool
    affected_entity_ids: list[int] = Field(default_factory=list)
    created_timeline_event_ids: list[int] = Field(default_factory=list)
    message: str = ""


# Resolve forward references (Pydantic v2 needs this when one
# model references another declared later in the same file).
StableMemoryEntityDetail.model_rebuild()
