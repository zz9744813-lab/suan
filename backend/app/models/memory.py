"""Memory system MVP tables (spec §8 / §14.4)."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def _utcnow() -> datetime:
    return datetime.utcnow()


class MemoryCharacter(Base):
    """A character known to the story (spec §8.1)."""

    __tablename__ = "memory_characters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120), index=True)
    aliases: Mapped[list[str]] = mapped_column(JSON, default=list)
    role: Mapped[str] = mapped_column(String(40), default="support")  # protagonist / heroine / villain / support
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)  # 热血 / 理智 / 隐忍 ...
    base_profile: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=_utcnow, onupdate=_utcnow)

    project: Mapped["Project"] = relationship(back_populates="characters")
    states: Mapped[list["MemoryCharacterState"]] = relationship(back_populates="character", cascade="all, delete-orphan", order_by="MemoryCharacterState.chapter_no.desc()")


class MemoryCharacterState(Base):
    """Dynamic state snapshot (spec §8.2)."""

    __tablename__ = "memory_character_states"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    character_id: Mapped[int] = mapped_column(ForeignKey("memory_characters.id", ondelete="CASCADE"), index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    chapter_no: Mapped[int] = mapped_column(Integer, index=True)
    current_location: Mapped[str | None] = mapped_column(String(200), default=None)
    current_faction: Mapped[str | None] = mapped_column(String(120), default=None)
    current_goal: Mapped[str | None] = mapped_column(String(500), default=None)
    injury_state: Mapped[str | None] = mapped_column(String(500), default=None)
    emotion_state: Mapped[str | None] = mapped_column(String(200), default=None)
    secrets: Mapped[list[str]] = mapped_column(JSON, default=list)
    misunderstandings: Mapped[list[str]] = mapped_column(JSON, default=list)
    relationships: Mapped[dict] = mapped_column(JSON, default=dict)
    owned_items: Mapped[list[str]] = mapped_column(JSON, default=list)
    abilities: Mapped[list[str]] = mapped_column(JSON, default=list)
    last_seen_chapter: Mapped[int | None] = mapped_column(Integer, default=None)
    source_step_id: Mapped[int | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)

    character: Mapped["MemoryCharacter"] = relationship(back_populates="states")


class MemoryForeshadow(Base):
    """Planted foreshadow track (spec §8.3)."""

    __tablename__ = "memory_foreshadows"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200), index=True)
    summary: Mapped[str] = mapped_column(Text, default="")
    planted_chapter: Mapped[int | None] = mapped_column(Integer, default=None)
    expected_payoff_chapter: Mapped[int | None] = mapped_column(Integer, default=None)
    actual_payoff_chapter: Mapped[int | None] = mapped_column(Integer, default=None)
    status: Mapped[str] = mapped_column(String(20), default="active")  # active / paid_off / dropped
    importance: Mapped[float] = mapped_column(Float, default=0.5)
    related_characters: Mapped[list[str]] = mapped_column(JSON, default=list)
    related_items: Mapped[list[str]] = mapped_column(JSON, default=list)
    related_main_plot: Mapped[str | None] = mapped_column(String(300), default=None)
    # R22: provenance. Set when a foreshadow was auto-extracted from a
    # study material by the bulk event extractor; lets the Study page
    # "this foreshadow came from 拆书《xxx》" tooltip and lets the graph
    # materialise endpoint pull the same rows back out as event nodes.
    # Nullable + ON DELETE SET NULL so dropping a study material doesn't
    # nuke the project's foreshadow history.
    source_material_id: Mapped[int | None] = mapped_column(
        ForeignKey("study_materials.id", ondelete="SET NULL"), index=True, default=None,
    )
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=_utcnow, onupdate=_utcnow)


class MemoryHardFact(Base):
    """A confirmed fact that should never be contradicted (spec §8.1)."""

    __tablename__ = "memory_hard_facts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    category: Mapped[str] = mapped_column(String(40), default="setting")
    fact: Mapped[str] = mapped_column(Text)
    source_chapter: Mapped[int | None] = mapped_column(Integer, default=None)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
