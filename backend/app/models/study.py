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

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
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
