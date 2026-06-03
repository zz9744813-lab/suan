"""Prompt template + version (spec §7 / §14.3)."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def _utcnow() -> datetime:
    return datetime.utcnow()


class PromptTemplate(Base):
    __tablename__ = "prompt_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    template_key: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(40), index=True)  # writing / review / ...
    role: Mapped[str] = mapped_column(String(40), index=True)  # DraftAgent / Critic / ...
    scope: Mapped[str] = mapped_column(String(20), default="project")
    genre: Mapped[str | None] = mapped_column(String(50), default=None)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    allowed_inputs: Mapped[list[str]] = mapped_column(JSON, default=list)
    forbidden_inputs: Mapped[list[str]] = mapped_column(JSON, default=list)
    output_schema: Mapped[str | None] = mapped_column(String(80), default=None)
    can_modify: Mapped[list[str]] = mapped_column(JSON, default=list)
    cannot_modify: Mapped[list[str]] = mapped_column(JSON, default=list)
    hard_rules: Mapped[list[str]] = mapped_column(JSON, default=list)
    active_version_id: Mapped[int | None] = mapped_column(default=None, index=True)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=_utcnow, onupdate=_utcnow)


class PromptVersion(Base):
    __tablename__ = "prompt_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    template_id: Mapped[int] = mapped_column(ForeignKey("prompt_templates.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer, index=True)
    body: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="active")  # active / candidate / deprecated
    change_note: Mapped[str | None] = mapped_column(Text, default=None)
    test_pass_rate: Mapped[float] = mapped_column(default=0.0)
    avg_score_delta: Mapped[float] = mapped_column(default=0.0)
    usage_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
