"""Study (拆书) / Behavior Pattern (行为模式) models.

The user can paste or upload a reference novel (a "study material"),
auto-segment it into chapters, and run the StudyAgent prompt to
extract characters. From those characters (plus the chapter text) the
BehaviorPatternAgent prompt produces reusable pattern cards that the
writing pipeline can reference via ``behavior_patterns``.

Schema (Round 5 MVP — graph tables are intentionally deferred):

  study_materials ──┐
                    ├── study_chapters (1:N, chapter rows)
                    └── study_characters (1:N, extracted characters)
  behavior_patterns  (independent library, can link to a material)

For the MVP we keep graph persistence out of scope: behavior_patterns
already capture the high-signal edges (character_tag × situation_tag
→ behavior), which is what the writing pipeline consumes. A real
knowledge graph with entity/relation tables can come later.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def _utcnow() -> datetime:
    return datetime.utcnow()


class StudyMaterial(Base):
    """A reference novel / light-novel / chapter dump the user wants to learn from.

    The user can paste the raw text into ``raw_text`` directly, or upload
    a ``.txt`` file (handled by the route layer). After the upload the
    user runs ``POST /api/study/materials/{id}/chapterize`` which splits
    the text by chapter headers and populates ``StudyChapter`` rows.
    """

    __tablename__ = "study_materials"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Optional link to a Project: materials can be either project-scoped
    # (only used by that project) or global (a shared reference library).
    project_id: Mapped[int | None] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"), index=True, default=None
    )
    title: Mapped[str] = mapped_column(String(200), default="")
    author: Mapped[str] = mapped_column(String(200), default="")
    source: Mapped[str] = mapped_column(String(40), default="paste")
    # ``paste`` | ``upload`` | ``url`` — kept for future-proofing. The MVP
    # only writes ``paste`` or ``upload``.
    raw_text: Mapped[str] = mapped_column(Text, default="")
    # Pipeline status of the latest run on this material:
    #   draft   — text was saved, no chapters yet
    #   ready   — chapterize succeeded, chapters exist
    #   failed  — chapterize or study errored; see ``error``
    status: Mapped[str] = mapped_column(String(20), default="draft")
    error: Mapped[str | None] = mapped_column(Text, default=None)
    # Cached count of chapters for quick list rendering. Updated by the
    # chapterize endpoint and on study-character extraction.
    chapter_count: Mapped[int] = mapped_column(Integer, default=0)
    character_count: Mapped[int] = mapped_column(Integer, default=0)
    extra: Mapped[dict | None] = mapped_column(JSON, default=None)
    # === P0-DeepStudy: book-shelf + DeepStudy coordination fields ===
    # ``study_status`` is the DeepStudy pipeline state (separate from
    # the older ``status`` which is the basic chapterize state). Values
    # are the DeepStudy state machine: empty / uploaded / chapterized
    # / studying / paused / review_required / completed / failed.
    # Default to ``empty`` for new materials and backfill all
    # existing rows to ``chapterized`` (chapterize succeeded) or
    # ``empty`` (no chapters) below in the column backfill.
    study_status: Mapped[str] = mapped_column(String(40), default="empty")
    # ``deepstudy_version`` records which DeepStudy pipeline version
    # last produced results for this material. ``None`` means the
    # material hasn't been DeepStudied yet.
    deepstudy_version: Mapped[str | None] = mapped_column(String(40), default=None)
    # ``shelf_category`` is a free-form grouping for the library UI
    # (e.g. "玄幻" / "都市" / "古典") so the user can organise the
    # shelf. Defaults to the project's genre or empty.
    shelf_category: Mapped[str | None] = mapped_column(String(80), default=None)
    # ``cover_theme`` is a per-book UI hint (gradient / accent) the
    # library page uses to differentiate book spines.
    cover_theme: Mapped[dict | None] = mapped_column(JSON, default=None)
    # ``study_progress`` is the live snapshot of the running run's
    # progress (total/processed chapters, current stage, counters).
    # Updated by the DeepStudy worker; cleared on completion.
    study_progress: Mapped[dict | None] = mapped_column(JSON, default=None)
    # ``knowledge_score`` is the latest StudyCritic score (0..1). Set
    # when a critic pass completes; ``None`` means no critic has run.
    knowledge_score: Mapped[float | None] = mapped_column(Float, default=None)
    # ``last_deepstudied_at`` is the timestamp of the most recent
    # successful DeepStudy run. ``None`` means the material has
    # never been DeepStudied.
    last_deepstudied_at: Mapped[datetime | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=_utcnow, onupdate=_utcnow)

    chapters: Mapped[list["StudyChapter"]] = relationship(
        back_populates="material", cascade="all, delete-orphan",
        order_by="StudyChapter.chapter_index",
    )
    characters: Mapped[list["StudyCharacter"]] = relationship(
        back_populates="material", cascade="all, delete-orphan",
    )


class StudyChapter(Base):
    """One chapter parsed from a ``StudyMaterial``.

    ``chapter_index`` is 1-based (the user thinks in chapters, not array
    indices). ``content`` is the raw chapter text; ``char_count`` is
    cached for fast UI rendering.
    """

    __tablename__ = "study_chapters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    material_id: Mapped[int] = mapped_column(
        ForeignKey("study_materials.id", ondelete="CASCADE"), index=True
    )
    chapter_index: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(200), default="")
    content: Mapped[str] = mapped_column(Text, default="")
    char_count: Mapped[int] = mapped_column(Integer, default=0)
    # ``stale`` is set by the study-character endpoint so the user can
    # re-run extraction on a chapter that's been edited.
    last_studied_at: Mapped[datetime | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)

    material: Mapped["StudyMaterial"] = relationship(back_populates="chapters")


class StudyCharacter(Base):
    """A character the StudyAgent identified in a chapter.

    Multiple ``StudyCharacter`` rows for the same person (e.g. a "主角"
    entry extracted from chapter 1 vs chapter 3) are kept distinct for
    now — the ``aliases`` field is the human-merged dedupe key. A future
    "merge" UI can collapse them.
    """

    __tablename__ = "study_characters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    material_id: Mapped[int] = mapped_column(
        ForeignKey("study_materials.id", ondelete="CASCADE"), index=True
    )
    source_chapter_id: Mapped[int | None] = mapped_column(
        ForeignKey("study_chapters.id", ondelete="SET NULL"), default=None
    )
    name: Mapped[str] = mapped_column(String(120), index=True)
    aliases: Mapped[list[str]] = mapped_column(JSON, default=list)
    role: Mapped[str] = mapped_column(String(40), default="其他")
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    base_profile: Mapped[dict | None] = mapped_column(JSON, default=None)
    # The LLM's own confidence score (0..1) — surfaced in the UI so
    # users can spot low-quality rows to delete.
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)

    material: Mapped["StudyMaterial"] = relationship(back_populates="characters")


class BehaviorPattern(Base):
    """A reusable behavior pattern card.

    The writing pipeline already references ``behavior_patterns`` in the
    Planner prompt; this table is the persistent home for those cards.
    Tags drive the query API: a user can ask for "主角 + 公开羞辱" and
    the backend returns every pattern whose ``character_tags`` and
    ``situation_tags`` intersect the requested set.
    """

    __tablename__ = "behavior_patterns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Optional link back to a study material so the UI can show "this
    # pattern came from 拆书《xxx》第 5 章". ``None`` for hand-authored rows.
    source_material_id: Mapped[int | None] = mapped_column(
        ForeignKey("study_materials.id", ondelete="SET NULL"), default=None
    )
    name: Mapped[str] = mapped_column(String(120), index=True)
    character_tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    situation_tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    typical_behavior: Mapped[list[str]] = mapped_column(JSON, default=list)
    dialogue_style: Mapped[list[str]] = mapped_column(JSON, default=list)
    scene_function: Mapped[list[str]] = mapped_column(JSON, default=list)
    risks: Mapped[list[str]] = mapped_column(JSON, default=list)
    recommended_plot_followup: Mapped[list[str]] = mapped_column(JSON, default=list)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    # Free-form evidence: short quoted snippets from the source material
    # that back the pattern. The MVP just stores the first 3 snippets.
    evidence: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=_utcnow, onupdate=_utcnow)


# ============================================================
# Round E (P1-1) — 人物关系图谱
# ============================================================
# A real knowledge graph: nodes are characters (linked to either a
# project_id or a study material), edges are typed relations
# (师父/对手/恋人/... — the user picks). This is the back-end of
# the new `/graph` page; the writing pipeline (Planner / Drafter) can
# later consume the graph for "what does this character already know
# about X" reasoning.
#
# The data model is intentionally generic: ``node_kind`` can be
# ``study_character`` (extracted by StudyCharacterAgent), ``project_character``
# (the project's own character roster — see memory.py), or
# ``faction`` / ``location`` for non-person entities. The UI renders
# all kinds in the same canvas with different colours.

class GraphNode(Base):
    """A node in the character/relation graph.

    For ``node_kind='study_character'`` the ``ref_study_character_id`` is
    set; for ``node_kind='project_character'`` the ``ref_character_id``
    (from ``MemoryCharacter``) is set. The two ``ref_*_id`` columns are
    nullable so we can also add hand-authored nodes that aren't linked
    to a project or study.
    """

    __tablename__ = "graph_nodes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # project scoping — a node belongs to a project OR is global (None).
    project_id: Mapped[int | None] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True, default=None
    )
    # Optional: a study material the node originated from. The graph page
    # uses this to surface "this character was extracted from 拆书《xxx》"
    # in the node tooltip.
    source_material_id: Mapped[int | None] = mapped_column(
        ForeignKey("study_materials.id", ondelete="SET NULL"), default=None
    )
    node_kind: Mapped[str] = mapped_column(String(40), default="study_character")
    # ``study_character`` | ``project_character`` | ``faction`` | ``location`` | ``other``
    name: Mapped[str] = mapped_column(String(120), index=True)
    # Optional cross-references: at most ONE of these is populated per row.
    ref_study_character_id: Mapped[int | None] = mapped_column(
        ForeignKey("study_characters.id", ondelete="SET NULL"), default=None
    )
    ref_character_id: Mapped[int | None] = mapped_column(
        ForeignKey("memory_characters.id", ondelete="SET NULL"), default=None
    )
    # Misc profile bag — same shape as StudyCharacter.base_profile, but
    # the user can hand-edit. Stored as JSON for forward-compat.
    extra: Mapped[dict | None] = mapped_column(JSON, default=None)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=_utcnow, onupdate=_utcnow)


class GraphEdge(Base):
    """A directed typed relation between two ``GraphNode`` rows.

    ``relation`` is a free-form string ("师父", "对手", "暗恋", ...). The
    graph page groups edges by relation in a sidebar so the user can
    toggle whole relationship families on/off.

    ``weight`` is a 0..1 confidence / strength score the LLM (or the
    user) assigns. The visualisation uses it for stroke thickness.
    """

    __tablename__ = "graph_edges"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int | None] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True, default=None
    )
    source_node_id: Mapped[int] = mapped_column(
        ForeignKey("graph_nodes.id", ondelete="CASCADE"), index=True,
    )
    target_node_id: Mapped[int] = mapped_column(
        ForeignKey("graph_nodes.id", ondelete="CASCADE"), index=True,
    )
    relation: Mapped[str] = mapped_column(String(60), index=True)
    weight: Mapped[float] = mapped_column(Float, default=0.5)
    count: Mapped[int] = mapped_column(Integer, default=1)
    # Optional short evidence quote backing the edge.
    evidence: Mapped[str | None] = mapped_column(Text, default=None)
    extra: Mapped[dict | None] = mapped_column(JSON, default=None)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=_utcnow, onupdate=_utcnow)

    source_node: Mapped["GraphNode"] = relationship(foreign_keys=[source_node_id])
    target_node: Mapped["GraphNode"] = relationship(foreign_keys=[target_node_id])

    __table_args__ = (
        UniqueConstraint("source_node_id", "target_node_id", "relation", name="uq_graph_edge"),
    )
