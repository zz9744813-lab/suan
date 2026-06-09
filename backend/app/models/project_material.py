"""项目资料上传与记忆拆解模型。"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def _utcnow() -> datetime:
    return datetime.utcnow()


class ProjectMaterial(Base):
    __tablename__ = "project_materials"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(240))
    filename: Mapped[str] = mapped_column(String(300), default="")
    material_type: Mapped[str] = mapped_column(String(60), default="other", index=True)
    mime_type: Mapped[str | None] = mapped_column(String(120), default=None)
    extracted_text: Mapped[str] = mapped_column(Text, default="")
    word_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(30), default="uploaded", index=True)
    ingest_summary: Mapped[str] = mapped_column(Text, default="")
    ingest_result: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(default=_utcnow, onupdate=_utcnow)


class ProjectMaterialIngestionRun(Base):
    __tablename__ = "project_material_ingestion_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    material_id: Mapped[int] = mapped_column(ForeignKey("project_materials.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(30), default="running", index=True)
    summary: Mapped[str] = mapped_column(Text, default="")
    result: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_counts: Mapped[dict[str, int]] = mapped_column(JSON, default=dict)
    error_message: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow, index=True)
    finished_at: Mapped[datetime | None] = mapped_column(default=None)
