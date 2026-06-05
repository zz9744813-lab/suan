"""Behavior Card (行为卡) models — P0 behavior-card-knowledge-base.

Each card represents a reusable character behavior pattern that can be
queried and injected by writing Agents (Planner / Drafter / Critic / Rewrite).
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# BehaviorCategory — shelf / grouping for cards
# ---------------------------------------------------------------------------
class BehaviorCategory(Base):
    __tablename__ = "behavior_categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    slug: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    icon: Mapped[str | None] = mapped_column(String(32), default=None)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_collapsed: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=_utcnow, onupdate=_utcnow)

    # relationships
    cards: Mapped[list["BehaviorCard"]] = relationship(
        back_populates="category", cascade="all, delete-orphan",
    )


# ---------------------------------------------------------------------------
# BehaviorCard — main card entity
# ---------------------------------------------------------------------------
class BehaviorCard(Base):
    __tablename__ = "behavior_cards"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("behavior_categories.id", ondelete="SET NULL"), default=None,
    )
    # FK to old behavior_patterns.id — populated by migration when a card
    # was auto-generated from the legacy table. ``None`` for hand-authored cards.
    source_pattern_id: Mapped[int | None] = mapped_column(Integer, nullable=True, default=None)
    name: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    role_type: Mapped[str | None] = mapped_column(String(80), default=None)
    status: Mapped[str] = mapped_column(String(40), default="ready")
    avatar_symbol: Mapped[str | None] = mapped_column(String(16), default=None)
    color_theme: Mapped[str | None] = mapped_column(String(40), default=None)

    # content fields
    summary: Mapped[str | None] = mapped_column(Text, default=None)
    typical_behavior: Mapped[str | None] = mapped_column(Text, default=None)
    emotion_chain: Mapped[str | None] = mapped_column(Text, default=None)
    behavior_chain: Mapped[str | None] = mapped_column(Text, default=None)
    dialogue_style: Mapped[str | None] = mapped_column(Text, default=None)
    suitable_scenes: Mapped[str | None] = mapped_column(Text, default=None)
    unsuitable_scenes: Mapped[str | None] = mapped_column(Text, default=None)
    injection_hint: Mapped[str | None] = mapped_column(Text, default=None)

    # counters
    source_count: Mapped[int] = mapped_column(Integer, default=0)
    technique_count: Mapped[int] = mapped_column(Integer, default=0)
    usage_count: Mapped[int] = mapped_column(Integer, default=0)

    # scores
    fit_score: Mapped[float] = mapped_column(Float, default=0)
    stability_score: Mapped[float] = mapped_column(Float, default=0)
    dialogue_score: Mapped[float] = mapped_column(Float, default=0)
    generalization_score: Mapped[float] = mapped_column(Float, default=0)

    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    last_used_at: Mapped[datetime | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=_utcnow, onupdate=_utcnow)

    # relationships
    category: Mapped["BehaviorCategory | None"] = relationship(back_populates="cards")
    tags: Mapped[list["BehaviorCardTag"]] = relationship(
        back_populates="card", cascade="all, delete-orphan",
    )
    techniques: Mapped[list["BehaviorCardTechnique"]] = relationship(
        back_populates="card", cascade="all, delete-orphan",
        order_by="BehaviorCardTechnique.priority",
    )
    sources: Mapped[list["BehaviorCardSource"]] = relationship(
        back_populates="card", cascade="all, delete-orphan",
    )
    usage_logs: Mapped[list["BehaviorCardUsageLog"]] = relationship(
        back_populates="card", cascade="all, delete-orphan",
    )


# ---------------------------------------------------------------------------
# BehaviorCardTag
# ---------------------------------------------------------------------------
class BehaviorCardTag(Base):
    __tablename__ = "behavior_card_tags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    card_id: Mapped[int] = mapped_column(
        ForeignKey("behavior_cards.id", ondelete="CASCADE"), nullable=False,
    )
    tag_type: Mapped[str] = mapped_column(String(40), nullable=False)  # role/scene/emotion/plot/source/style
    tag_name: Mapped[str] = mapped_column(String(80), nullable=False)
    weight: Mapped[float] = mapped_column(Float, default=1.0)

    created_at: Mapped[datetime] = mapped_column(default=_utcnow)

    card: Mapped["BehaviorCard"] = relationship(back_populates="tags")


# ---------------------------------------------------------------------------
# BehaviorCardTechnique — distilled writing technique
# ---------------------------------------------------------------------------
class BehaviorCardTechnique(Base):
    __tablename__ = "behavior_card_techniques"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    card_id: Mapped[int] = mapped_column(
        ForeignKey("behavior_cards.id", ondelete="CASCADE"), nullable=False,
    )
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    example: Mapped[str | None] = mapped_column(Text, default=None)
    priority: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=_utcnow, onupdate=_utcnow)

    card: Mapped["BehaviorCard"] = relationship(back_populates="techniques")


# ---------------------------------------------------------------------------
# BehaviorCardSource — evidence from study analysis
# ---------------------------------------------------------------------------
class BehaviorCardSource(Base):
    __tablename__ = "behavior_card_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    card_id: Mapped[int] = mapped_column(
        ForeignKey("behavior_cards.id", ondelete="CASCADE"), nullable=False,
    )
    book_id: Mapped[int | None] = mapped_column(Integer, default=None)
    book_title: Mapped[str | None] = mapped_column(String(200), default=None)
    chapter_title: Mapped[str | None] = mapped_column(String(200), default=None)
    source_type: Mapped[str] = mapped_column(String(40), default="book_analysis")
    source_excerpt: Mapped[str | None] = mapped_column(Text, default=None)
    extracted_summary: Mapped[str | None] = mapped_column(Text, default=None)
    confidence: Mapped[float] = mapped_column(Float, default=0)

    created_at: Mapped[datetime] = mapped_column(default=_utcnow)

    card: Mapped["BehaviorCard"] = relationship(back_populates="sources")


# ---------------------------------------------------------------------------
# BehaviorCardUsageLog — track writing agent usage
# ---------------------------------------------------------------------------
class BehaviorCardUsageLog(Base):
    __tablename__ = "behavior_card_usage_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    card_id: Mapped[int] = mapped_column(
        ForeignKey("behavior_cards.id", ondelete="CASCADE"), nullable=False,
    )
    project_id: Mapped[int | None] = mapped_column(Integer, default=None)
    chapter_id: Mapped[int | None] = mapped_column(Integer, default=None)
    task_id: Mapped[int | None] = mapped_column(Integer, default=None)
    agent_role: Mapped[str | None] = mapped_column(String(80), default=None)
    usage_type: Mapped[str | None] = mapped_column(String(80), default=None)
    prompt_excerpt: Mapped[str | None] = mapped_column(Text, default=None)
    output_excerpt: Mapped[str | None] = mapped_column(Text, default=None)
    feedback_score: Mapped[float | None] = mapped_column(Float, default=None)

    created_at: Mapped[datetime] = mapped_column(default=_utcnow)

    card: Mapped["BehaviorCard"] = relationship(back_populates="usage_logs")
