"""P7: Genre-Prompt mapping + Prompt snapshot (traceability).

Two tables:
  - GenrePromptMapping: Agent × Genre → PromptTemplate binding (drag-drop matrix)
  - ProjectPromptSnapshot: per-chapter snapshot of which prompts were used
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def _utcnow() -> datetime:
    return datetime.utcnow()


# ============================================================
# GenrePromptMapping (P7 §7.0a) — Agent × Genre → PromptTemplate
# ============================================================
class GenrePromptMapping(Base):
    """Binds a specific prompt template to an (agent_role_key, genre) pair.

    genre="" (empty string) means "generic fallback" for that agent role.
    When an agent runs for a project with genre=X, the engine first looks
    for a mapping with genre=X, then falls back to genre="".
    """

    __tablename__ = "genre_prompt_mappings"
    __table_args__ = (
        UniqueConstraint(
            "agent_role_key", "genre", "prompt_template_id",
            name="uq_genre_prompt_mapping",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    agent_role_key: Mapped[str] = mapped_column(String(80), index=True)
    genre: Mapped[str] = mapped_column(String(50), index=True)  # "" = generic fallback
    prompt_template_id: Mapped[int] = mapped_column(
        ForeignKey("prompt_templates.id", ondelete="CASCADE"), index=True,
    )
    priority: Mapped[int] = mapped_column(Integer, default=0)   # higher = preferred
    sort_order: Mapped[int] = mapped_column(Integer, default=0)  # UI drag order
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=_utcnow, onupdate=_utcnow)


# ============================================================
# ProjectPromptSnapshot (P7 §7.0b) — Traceability
# ============================================================
class ProjectPromptSnapshot(Base):
    """Snapshot of prompt bindings at the moment a chapter pipeline runs.

    Records which template (key, id, version, genre) each agent used,
    so the user can audit "which prompt produced this chapter?".
    """

    __tablename__ = "project_prompt_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True,
    )
    chapter_id: Mapped[int | None] = mapped_column(
        ForeignKey("chapters.id", ondelete="SET NULL"), default=None, index=True,
    )
    chapter_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("chapter_versions.id", ondelete="SET NULL"), default=None,
    )
    trigger: Mapped[str] = mapped_column(String(40), default="chapter_pipeline")
    # {"drafter": {"template_key": "...", "template_id": 45, "version": 3, "genre": "科幻"}, ...}
    snapshot_data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow, index=True)
