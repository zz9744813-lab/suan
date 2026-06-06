"""Schemas for the Study (拆书) / Behavior Pattern MVP."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


# -------------------- StudyMaterial --------------------

class StudyMaterialCreate(BaseModel):
    """Create a study material by pasting the raw text.

    The MVP supports two ingestion paths from the same payload:
      - ``source="paste"`` (default): the client sends ``raw_text``
        inline (≤ ~5 MB; bigger uploads go through the multipart route).
      - ``source="upload"``: a separate file-upload route writes the
        bytes to disk and then inserts the row with ``raw_text`` empty
        and a pointer in ``extra["file_path"]``.
    """
    title: str = Field(..., min_length=1, max_length=200)
    author: str = ""
    source: Literal["paste", "upload", "url"] = "paste"
    project_id: int | None = None
    raw_text: str = ""


class StudyMaterialUpdate(BaseModel):
    title: str | None = None
    author: str | None = None
    project_id: int | None = None
    raw_text: str | None = None


class StudyMaterialRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int | None
    title: str
    author: str
    source: str
    status: str
    error: str | None
    chapter_count: int
    character_count: int
    study_status: str = "empty"
    deepstudy_version: str | None = None
    shelf_category: str | None = None
    cover_theme: dict[str, Any] | None = None
    study_progress: dict[str, Any] | None = None
    knowledge_score: float | None = None
    last_deepstudied_at: datetime | None = None
    # Don't serialise the full raw_text on the list endpoint — a 5 MB
    # novel bloats every list response. The detail endpoint can opt in
    # via ``?include_text=1``.
    raw_text_length: int = 0
    extra: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_orm_trimmed(cls, obj, *, include_text: bool = False) -> "StudyMaterialRead":
        return cls(
            id=obj.id,
            project_id=obj.project_id,
            title=obj.title,
            author=obj.author,
            source=obj.source,
            status=obj.status,
            error=obj.error,
            chapter_count=obj.chapter_count,
            character_count=obj.character_count,
            study_status=obj.study_status or "empty",
            deepstudy_version=obj.deepstudy_version,
            shelf_category=obj.shelf_category,
            cover_theme=obj.cover_theme,
            study_progress=obj.study_progress,
            knowledge_score=obj.knowledge_score,
            last_deepstudied_at=obj.last_deepstudied_at,
            raw_text_length=len(obj.raw_text or "") if not include_text else 0,
            extra=obj.extra,
            created_at=obj.created_at,
            updated_at=obj.updated_at,
        )


class StudyMaterialDetail(StudyMaterialRead):
    """Detail view that includes the raw_text and chapter list."""
    raw_text: str = ""
    chapters: list["StudyChapterRead"] = Field(default_factory=list)
    characters: list["StudyCharacterRead"] = Field(default_factory=list)


# -------------------- StudyChapter --------------------

class StudyChapterRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    material_id: int
    chapter_index: int
    title: str
    content: str
    char_count: int
    last_studied_at: datetime | None
    created_at: datetime


class ChapterizeRequest(BaseModel):
    """Optional knobs for the chapterize step. Most callers leave this empty."""
    min_chapter_chars: int = 50
    pattern: Literal["auto", "chinese", "english"] = "auto"


# -------------------- StudyCharacter --------------------

class StudyCharacterRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    material_id: int
    source_chapter_id: int | None
    name: str
    aliases: list[str]
    role: str
    tags: list[str]
    base_profile: dict[str, Any] | None
    confidence: float
    created_at: datetime


class StudyCharacterCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    aliases: list[str] = Field(default_factory=list)
    role: str = "其他"
    tags: list[str] = Field(default_factory=list)
    base_profile: dict[str, Any] | None = None
    confidence: float = 0.5


class StudyRequest(BaseModel):
    """Run character extraction on one chapter.

    ``max_chars`` caps the LLM prompt (the Study prompt can blow up on
    a 50K-char chapter; we keep only the first N to stay cheap).
    """
    chapter_id: int
    max_chars: int = 8000


class StudyBulkRequest(BaseModel):
    """R21: bulk character / event extraction across ALL chapters of a
    material.

    The endpoint spawns a background task and returns immediately. The
    caller polls ``GET /api/tasks/{task_id}`` to see progress — the
    AgentTask's ``payload`` carries the per-mode counters
    (chapters_processed / chapters_total / characters_added /
    events_added / errors).
    """
    # What to extract. ``character`` is the cheap default; ``event``
    # requires the material to be associated with a project_id (so the
    # extracted foreshadows have a home in memory_foreshadows).
    # ``both`` runs both in one pass per chapter.
    mode: Literal["character", "event", "both"] = "character"
    # Cap on chapters to process this round; 0 = no cap (default).
    # The frontend uses this to process e.g. 50 chapters at a time
    # so the user can throttle long books like 蛊真人 (2332 节).
    limit: int = 0
    # In-flight parallel LLM calls per chapter. 3 is a sweet spot
    # — the cheap model gives ~18 tok/s, so 3 in flight roughly
    # saturates one chapter's worth of LLM bandwidth.
    max_concurrency: int = 3
    # Re-run extraction on chapters that already have last_studied_at.
    # Default False so a re-click doesn't double-charge LLM tokens.
    force: bool = False
    # Per-chapter cap on the prompt length, same semantics as
    # ``StudyRequest.max_chars``.
    max_chars: int = 8000


class StudyBulkStartResponse(BaseModel):
    """R21: the immediate response from ``POST .../study/all``."""
    task_id: int
    total_chapters: int
    chapters_to_process: int
    mode: str
    message: str = "后台处理中。可轮询 /api/tasks/{task_id} 看进度。"


# -------------------- R22: behavior extraction --------------------

class StudyBehaviorExtractRequest(BaseModel):
    """R22: kick off a whole-material behavior-pattern extraction.

    The single LLM call sees the material's character roster + a
    digest of representative chapter snippets and returns reusable
    ``{character × situation}`` pattern cards. We persist the result
    into ``behavior_patterns`` with ``source_material_id`` so the
    drafter can pull them by tag during chapter generation.
    """
    # Cap on patterns to keep. Default 20 — the LLM doesn't always
    # respect the cap, so the route truncates after the fact.
    max_patterns: int = 20
    # Re-run on a material that already has patterns. Default False
    # so the user's first click is the canonical extraction; a
    # re-click with force=True discards the old set for this material.
    force: bool = False
    # Truncate each evidence chunk to this many characters before
    # shipping to the LLM. Cheap models on long contexts start
    # dropping characters; 1500 is enough to keep the prompt
    # focused on the 2-3 scenes the agent should reason about.
    max_chunk_chars: int = 1500
    # How many chapter snippets to include in evidence. The router
    # picks the chapters with the most extracted characters (i.e.
    # the most "active" scenes) so the agent reasons about the
    # material's pivotal moments, not its opening or coda.
    evidence_chapter_count: int = 5


class StudyBehaviorExtractResponse(BaseModel):
    """R22: the immediate response from extract-behaviors.

    ``pattern_ids`` are the rows the route just inserted, so the UI
    can scroll-jump to them in the Behavior page.
    """
    material_id: int
    patterns_added: int
    patterns_skipped: int
    pattern_ids: list[int]
    total_patterns_for_material: int
    cost_usd: float
    duration_ms: int
    input_tokens: int
    output_tokens: int
    sample_names: list[str] = Field(default_factory=list)


# -------------------- R22: relationship suggestions --------------------

class StudyRelationshipSuggestion(BaseModel):
    """One suggested edge between two characters that co-occur in the
    same chapter.

    ``co_chapter_count`` is how many chapters both names appear in
    (capped at 1 in the MVP — we just want a yes/no "they share a
    scene" signal). ``last_chapter_no`` is the most recent chapter
    index where the pair co-occurs; the UI surfaces it so the user
    can see at a glance where the relationship originates.
    """
    char_a_id: int
    char_a_name: str
    char_b_id: int
    char_b_name: str
    co_chapter_count: int
    last_chapter_id: int
    last_chapter_no: int
    last_chapter_title: str
    sample_quote: str = ""


class StudyRelationshipsResponse(BaseModel):
    """R22: the response from ``GET .../relationships``.

    ``chapters_scanned`` is how many of the material's chapters we
    actually ran co-occurrence against. The MVP scans all of them
    but a future cap can trim it for very large books.
    """
    material_id: int
    chapters_scanned: int
    suggestions: list[StudyRelationshipSuggestion]
    total_characters: int
    min_co_chapter_count: int = 1


class StudyRelationshipApplyRequest(BaseModel):
    """R22: the user picked N of the suggested relationships and we
    now create them as ``GraphEdge`` rows.
    """
    project_id: int
    # The pair list — each is (char_a_id, char_b_id, relation).
    # ``relation`` is free-form ("师父" / "同门" / ...) so the user
    # can label the edge however they like.
    pairs: list[dict[str, Any]] = Field(default_factory=list)


class StudyRelationshipApplyResponse(BaseModel):
    """R22: how many edges were created (and skipped)."""
    project_id: int
    edges_added: int
    edges_skipped: int
    edge_ids: list[int]


# -------------------- R22: study material overview --------------------

class StudyMaterialOverview(BaseModel):
    """R22: one-shot dashboard of a study material.

    Aggregates the "where did the data go" question so the Study
    page can show a 4-stat row (chapters / characters / behaviors /
    foreshadows) and a "already on the graph" badge without making
    four round-trips.
    """
    material_id: int
    title: str
    project_id: int | None
    chapter_count: int
    character_count: int
    behavior_count: int
    foreshadow_count: int
    graph_node_count: int
    # First few of each, for tooltip / click-through. Capped at 5
    # so the payload stays small.
    sample_characters: list[dict[str, Any]] = Field(default_factory=list)
    sample_behaviors: list[dict[str, Any]] = Field(default_factory=list)
    sample_foreshadows: list[dict[str, Any]] = Field(default_factory=list)


# -------------------- R22: materialise summary + foreshadow summary --------------------

class MaterialiseSummary(BaseModel):
    """R22: counts surfaced by ``POST /api/graph/{pid}/materialise_from_study/{mid}``.

    The route returns the standard ``APIResponse`` envelope (with
    ``data`` carrying the full graph bundle) AND this sibling field
    so the UI can show "新增 X 节点 / Y 关系" without re-fetching
    the whole graph. Strict ``APIResponse[GraphBundle]`` would
    strip the field, so the route's ``response_model=None``.
    """
    nodes_created: int
    edges_created: int


class StudyForeshadowSummary(BaseModel):
    """R22: the narrow shape ``GET /api/study/materials/{id}/foreshadows`` returns.

    Only the columns the Study page actually renders — fuller
    columns (expected_payoff_chapter / related_items / related_main_plot)
    are available on the memory page. Keeping this lean lets the
    study overview render the "events from this book" list without
    hauling 5KB of unrelated JSON for each row.
    """
    id: int
    name: str
    summary: str
    planted_chapter: int | None
    status: str
    importance: float
    related_characters: list[str] = Field(default_factory=list)


# -------------------- R24: 关系语义抽取 --------------------

class StudyRelationshipEnrichRequest(BaseModel):
    """R24: 对 R22 的纯 co-occurrence suggestions 跑 LLM 抽取
    真正的语义关系 (师父/对手/恋人/朋友/家人/... 而不是「同
    章节出现」)。"""
    suggestion_ids: list[int] = Field(
        default_factory=list,
        description=(
            "要 LLM 重新分类的 suggestion ids (后端是顺序对, 不是 "
            "真用 id; 传了就只跑这些, 传空就跑全部"
        ),
    )
    min_co_chapter_count: int = 1
    max_pairs: int = 30  # 一次最多跑 30 对, 防止 LLM 调用爆炸


class StudyRelationshipEnrichedItem(BaseModel):
    """R24: 一对 (char_a, char_b) 的语义关系结果。"""
    char_a_id: int
    char_a_name: str
    char_b_id: int
    char_b_name: str
    co_chapter_count: int
    last_chapter_no: int
    last_chapter_title: str
    # R22 的旧字段, 保留以便前端能 diff
    sample_quote: str
    # R24 新增
    relation: str = "同章节出现"   # 实际语义关系
    confidence: float = 0.0
    evidence: str = ""
    llm_inferred: bool = False     # True = LLM 抽出来的, False = 纯 co-occurrence 兜底


class StudyRelationshipEnrichResponse(BaseModel):
    """R24: LLM 抽取完成后的回包。"""
    material_id: int
    enriched_count: int
    skipped_count: int           # 没 LLM 调用 (sample 之外 / 已知关系 / 错误)
    fallback_count: int          # LLM 返回空 / 关系标 "未知" 的
    duration_ms: int
    cost_usd: float
    items: list[StudyRelationshipEnrichedItem]


# -------------------- BehaviorPattern --------------------

class BehaviorPatternRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source_material_id: int | None
    name: str
    character_tags: list[str]
    situation_tags: list[str]
    typical_behavior: list[str]
    dialogue_style: list[str]
    scene_function: list[str]
    risks: list[str]
    recommended_plot_followup: list[str]
    confidence: float
    evidence: list[str]
    created_at: datetime
    updated_at: datetime


class BehaviorPatternCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    character_tags: list[str] = Field(default_factory=list)
    situation_tags: list[str] = Field(default_factory=list)
    typical_behavior: list[str] = Field(default_factory=list)
    dialogue_style: list[str] = Field(default_factory=list)
    scene_function: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    recommended_plot_followup: list[str] = Field(default_factory=list)
    confidence: float = 0.5
    evidence: list[str] = Field(default_factory=list)
    source_material_id: int | None = None


class BehaviorPatternUpdate(BaseModel):
    name: str | None = None
    character_tags: list[str] | None = None
    situation_tags: list[str] | None = None
    typical_behavior: list[str] | None = None
    dialogue_style: list[str] | None = None
    scene_function: list[str] | None = None
    risks: list[str] | None = None
    recommended_plot_followup: list[str] | None = None
    confidence: float | None = None
    evidence: list[str] | None = None


# ============================================================
# Round E (P1-1) — 人物关系图谱 GraphNode / GraphEdge
# ============================================================

class GraphNodeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int | None
    source_material_id: int | None
    node_kind: str
    name: str
    ref_study_character_id: int | None
    ref_character_id: int | None
    extra: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime


class GraphNodeCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    node_kind: Literal[
        "study_character", "project_character", "faction", "location", "other"
    ] = "study_character"
    project_id: int | None = None
    source_material_id: int | None = None
    ref_study_character_id: int | None = None
    ref_character_id: int | None = None
    extra: dict[str, Any] | None = None


class GraphNodeUpdate(BaseModel):
    name: str | None = None
    node_kind: Literal[
        "study_character", "project_character", "faction", "location", "other"
    ] | None = None
    extra: dict[str, Any] | None = None


class GraphEdgeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int | None
    source_node_id: int
    target_node_id: int
    relation: str
    weight: float
    evidence: str | None
    extra: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime


class GraphEdgeCreate(BaseModel):
    source_node_id: int
    target_node_id: int
    relation: str = Field(..., min_length=1, max_length=60)
    weight: float = 0.5
    project_id: int | None = None
    evidence: str | None = None
    extra: dict[str, Any] | None = None


class GraphEdgeUpdate(BaseModel):
    relation: str | None = None
    weight: float | None = None
    evidence: str | None = None
    extra: dict[str, Any] | None = None


# Convenience: the graph page wants a single ``/api/graph`` payload
# with the full adjacency list, not separate node/edge round-trips.
class GraphBundle(BaseModel):
    """One project's full graph (nodes + edges) for the canvas."""
    nodes: list[GraphNodeRead] = Field(default_factory=list)
    edges: list[GraphEdgeRead] = Field(default_factory=list)


# Resolve the forward references in StudyMaterialDetail.
StudyMaterialDetail.model_rebuild()
