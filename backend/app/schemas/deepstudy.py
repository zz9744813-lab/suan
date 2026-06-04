"""DeepStudy module (R25 / P0) — Pydantic schemas.

Mirrors ``app/models/deepstudy.py`` plus a handful of
request/response shapes the route layer needs. Kept thin: the
``Entity``, ``SceneBeat``, ``Relationship`` etc. pydantic models
are deliberately permissive (``extra='allow'``) so the LLM can
add a field we haven't enumerated without blowing up the parse.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


# ============================================================
# Library (book-shelf) — section 6.1 of the spec
# ============================================================

class LibraryItem(BaseModel):
    """One row in the library list — a book spine on the shelf.

    Carries the full set of counters the UI needs to render the
    spine without making 6 more round-trips. ``knowledge_score``
    is the StudyCritic's last score (None if no critic has run
    yet); ``cost_usd`` is the cumulative cost across all runs.
    """
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    author: str = ""
    shelf_category: str | None = None
    cover_theme: dict | None = None
    # DeepStudy state machine value: empty / uploaded / chapterized
    # / studying / paused / review_required / completed / failed
    study_status: str = "empty"
    deepstudy_version: str | None = None
    chapter_count: int = 0
    processed_chapters: int = 0
    entity_count: int = 0
    # The following five are the "deep" counters — populated lazily
    # by subqueries in the library endpoint so the shelf page
    # doesn't have to fan-out N requests.
    scene_beat_count: int = 0
    relationship_count: int = 0
    foreshadow_count: int = 0
    behavior_count: int = 0
    technique_count: int = 0
    knowledge_score: float | None = None
    last_deepstudied_at: datetime | None = None
    cost_usd: float = 0.0
    project_id: int | None = None
    created_at: datetime
    updated_at: datetime


class LibrarySummary(BaseModel):
    """Top-of-shelf totals — the small "12 本 / 4 完成 / 2 拆中"
    strip at the top of the library page.
    """
    total_books: int = 0
    completed: int = 0
    studying: int = 0
    paused: int = 0
    review_required: int = 0
    failed: int = 0
    empty: int = 0
    chapterized: int = 0
    total_entities: int = 0
    total_relationships: int = 0
    total_techniques: int = 0
    total_cost_usd: float = 0.0


class LibraryResponse(BaseModel):
    items: list[LibraryItem]
    summary: LibrarySummary
    page: int = 1
    page_size: int = 50
    total: int = 0


# ============================================================
# Run lifecycle — sections 6.2 / 6.3 / 6.4
# ============================================================

class StudyRunCreate(BaseModel):
    """Body for ``POST /api/deepstudy/materials/{id}/runs``.

    ``mode`` controls which stages run:
      - full: chapter_profile + entity + scene_beat + relationship
              + foreshadow + behavior + technique + graph + critic
      - entities_only: chapter_profile + entity + scene_beat
      - relationships_only: chapter_profile + relationship
      - behaviors_only: chapter_profile + behavior
      - techniques_only: behavior + technique
      - repair_failed: re-run only the failed stages of the latest
                       run on this material.
    """
    # Pydantic v2 reserves ``model_*`` for its own config; the
    # spec uses ``model_roles`` to override per-role bindings, so
    # we drop the protected namespace on this schema only.
    model_config = ConfigDict(protected_namespaces=())

    mode: Literal[
        "full", "entities_only", "relationships_only",
        "behaviors_only", "techniques_only", "repair_failed",
    ] = "full"
    # Optional 1-based chapter range. ``None`` = whole book.
    chapter_range: list[int] | None = None
    # Re-run from scratch (drop prior run's derived rows on the
    # affected tables). Default False so a click is incremental.
    force: bool = False
    # Up to 8 concurrent per-chapter LLM calls. 3 is a sane default
    # for the cheap model (≈ 18 tok/s on this host).
    max_concurrency: int = 3
    # Override which LLM role the coordinator dispatches to. ``None``
    # = use whatever's bound to "StudyAgent" in the model_roles table.
    model_roles: dict[str, str] | None = None


class StudyRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    material_id: int
    project_id: int | None
    status: str
    mode: str
    total_chapters: int
    processed_chapters: int
    current_stage: str | None
    agent_plan: dict | None
    progress: dict | None
    cost_usd: float
    input_tokens: int
    output_tokens: int
    error: str | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime
    updated_at: datetime


class StudyRunStartResponse(BaseModel):
    """Immediate response for ``POST /runs`` — the caller polls
    ``GET /api/deepstudy/runs/{id}`` to see progress.
    """
    run_id: int
    material_id: int
    status: str
    message: str = "后台处理中。可轮询 /api/deepstudy/runs/{id} 看进度。"


# ============================================================
# Knowledge graph — section 6.5
# ============================================================

class GraphNodeRead(BaseModel):
    """One node in the per-book knowledge graph.

    ``id`` is a stringified composite key like ``"book:1"`` /
    ``"entity:33"`` / ``"scene:55"`` / ``"foreshadow:7"`` so the
    frontend can pattern-match on the prefix for icon / colour
    decisions. ``size`` is a render hint the layout uses to scale
    the node (derived from importance / degree). ``score`` is
    confidence so the UI can dim low-confidence nodes.
    """
    id: str
    type: str
    label: str
    size: int = 10
    score: float = 0.5
    chapter_index: int | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


class GraphEdgeRead(BaseModel):
    """One edge in the per-book knowledge graph.

    ``id`` is ``"{kind}:{row_id}"`` so it's stable across reloads.
    ``weight`` is the strength / evidence density (0..1).
    """
    id: str
    source: str
    target: str
    type: str
    label: str = ""
    weight: float = 0.5
    evidence: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


class KnowledgeGraphStats(BaseModel):
    nodes: int = 0
    edges: int = 0
    by_type: dict[str, int] = Field(default_factory=dict)


class KnowledgeGraphResponse(BaseModel):
    book: dict[str, Any]
    nodes: list[GraphNodeRead]
    edges: list[GraphEdgeRead]
    stats: KnowledgeGraphStats


# ============================================================
# Node detail — section 6.6
# ============================================================

class NodeDetailResponse(BaseModel):
    """Full payload for a clicked graph node — the right-side
    detail panel. ``agent_steps`` carries the audit trail so the
    user can see "this entity was extracted by EntityAgent run 47
    with confidence 0.82" — useful for the review_required flow.
    """
    id: str
    type: str
    label: str
    profile: dict[str, Any] = Field(default_factory=dict)
    mentions: list[dict[str, Any]] = Field(default_factory=list)
    relationships: list[dict[str, Any]] = Field(default_factory=list)
    scene_beats: list[dict[str, Any]] = Field(default_factory=list)
    foreshadows: list[dict[str, Any]] = Field(default_factory=list)
    behavior_patterns: list[dict[str, Any]] = Field(default_factory=list)
    techniques: list[dict[str, Any]] = Field(default_factory=list)
    agent_steps: list[dict[str, Any]] = Field(default_factory=list)


# ============================================================
# Pattern / technique libraries — sections 6.7 / 6.8
# ============================================================

class BehaviorPatternQuery(BaseModel):
    material_id: int | None = None
    character_tag: str | None = None
    situation_tag: str | None = None
    q: str | None = None
    min_confidence: float = 0.0
    limit: int = 50


class WritingTechniqueQuery(BaseModel):
    material_id: int | None = None
    technique_type: str | None = None
    situation: str | None = None
    q: str | None = None
    limit: int = 50
