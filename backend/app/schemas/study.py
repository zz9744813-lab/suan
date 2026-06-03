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
