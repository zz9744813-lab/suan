"""Project / chapter / bible / outline models.

These tables cover the project-management surfaces required by spec §14.1
and feed every downstream pipeline (ContextCompiler, Worker, Memory, etc.).
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def _utcnow() -> datetime:
    return datetime.utcnow()


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), index=True)
    genre: Mapped[str] = mapped_column(String(50), default="玄幻")
    target_word_count: Mapped[int] = mapped_column(Integer, default=3_000_000)
    target_chapter_count: Mapped[int] = mapped_column(Integer, default=2000)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    status: Mapped[str] = mapped_column(String(20), default="active")
    # Round 2 (P0-UI-2 / P0-UI-3) — project grouping, sort, pin, MRU.
    # category is the user-visible bucket key in the ProjectNav
    # (defaults to ``genre`` so existing projects get auto-grouped).
    # sort_order drives the order within a category; pinned items
    # float to the top regardless of sort_order. last_opened_at is
    # the MRU timestamp the chief-agent panel uses to suggest
    # recently-touched projects.
    category: Mapped[str | None] = mapped_column(String(80), default=None)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    pinned: Mapped[bool] = mapped_column(default=False)
    last_opened_at: Mapped[datetime | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=_utcnow, onupdate=_utcnow)

    chapters: Mapped[list["Chapter"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    bibles: Mapped[list["Bible"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    outlines: Mapped[list["Outline"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    characters: Mapped[list["MemoryCharacter"]] = relationship(back_populates="project", cascade="all, delete-orphan")


class Bible(Base):
    __tablename__ = "bibles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(200), default="主设定")
    content: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    version: Mapped[int] = mapped_column(Integer, default=1)
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=_utcnow, onupdate=_utcnow)

    project: Mapped["Project"] = relationship(back_populates="bibles")


class Outline(Base):
    __tablename__ = "outlines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    volume_no: Mapped[int] = mapped_column(Integer, default=1)
    chapter_no: Mapped[int] = mapped_column(Integer, index=True)
    title: Mapped[str] = mapped_column(String(200))
    summary: Mapped[str | None] = mapped_column(Text, default=None)
    importance: Mapped[int] = mapped_column(Integer, default=50)  # 0-100, triggers discussion
    is_arc_peak: Mapped[bool] = mapped_column(default=False)
    is_volume_climax: Mapped[bool] = mapped_column(default=False)
    is_volume_opener: Mapped[bool] = mapped_column(default=False)
    target_word_count: Mapped[int] = mapped_column(Integer, default=3000)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending / writing / done
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)

    project: Mapped["Project"] = relationship(back_populates="outlines")


class Chapter(Base):
    __tablename__ = "chapters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    outline_id: Mapped[int | None] = mapped_column(ForeignKey("outlines.id", ondelete="SET NULL"), default=None)
    chapter_no: Mapped[int] = mapped_column(Integer, index=True)
    title: Mapped[str] = mapped_column(String(200))
    target_word_count: Mapped[int] = mapped_column(Integer, default=3000)
    actual_word_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="queued")
    # queued / drafting / reviewing / rewriting / done / failed
    current_score: Mapped[int | None] = mapped_column(Integer, default=None)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=_utcnow, onupdate=_utcnow)

    project: Mapped["Project"] = relationship(back_populates="chapters")
    versions: Mapped[list["ChapterVersion"]] = relationship(back_populates="chapter", cascade="all, delete-orphan")
    tasks: Mapped[list["AgentTask"]] = relationship(back_populates="chapter", cascade="all, delete-orphan")


class ChapterVersion(Base):
    __tablename__ = "chapter_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chapter_id: Mapped[int] = mapped_column(ForeignKey("chapters.id", ondelete="CASCADE"))
    version_kind: Mapped[str] = mapped_column(String(20))  # draft / rewrite / final
    version_no: Mapped[int] = mapped_column(Integer, default=1)
    content: Mapped[str] = mapped_column(Text, default="")
    summary: Mapped[str | None] = mapped_column(Text, default=None)
    score: Mapped[int | None] = mapped_column(Integer, default=None)
    notes: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=None)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)

    chapter: Mapped["Chapter"] = relationship(back_populates="versions")
