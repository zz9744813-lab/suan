"""Project / chapter / bible / outline schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ProjectCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    genre: str = Field(default="玄幻")
    target_word_count: int = Field(default=3_000_000, ge=10_000)
    target_chapter_count: int = Field(default=2000, ge=10)
    description: str | None = None


class ProjectUpdate(BaseModel):
    name: str | None = None
    genre: str | None = None
    target_word_count: int | None = None
    target_chapter_count: int | None = None
    description: str | None = None
    status: str | None = None


class ProjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    genre: str
    target_word_count: int
    target_chapter_count: int
    description: str | None
    status: str
    created_at: datetime
    updated_at: datetime
    chapter_count: int = 0
    total_words: int = 0


class BibleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    title: str
    content: dict[str, Any]
    version: int
    is_active: bool
    updated_at: datetime


class BibleUpdate(BaseModel):
    title: str | None = None
    content: dict[str, Any] | None = None


class OutlineCreate(BaseModel):
    volume_no: int = 1
    chapter_no: int
    title: str
    summary: str | None = None
    importance: int = 50
    is_arc_peak: bool = False
    is_volume_climax: bool = False
    is_volume_opener: bool = False
    target_word_count: int = 3000


class OutlineRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    volume_no: int
    chapter_no: int
    title: str
    summary: str | None
    importance: int
    is_arc_peak: bool
    is_volume_climax: bool
    is_volume_opener: bool
    target_word_count: int
    status: str


class ChapterCreate(BaseModel):
    outline_id: int | None = None
    chapter_no: int
    title: str
    target_word_count: int = 3000


class ChapterRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    outline_id: int | None
    chapter_no: int
    title: str
    target_word_count: int
    actual_word_count: int
    status: str
    current_score: int | None
    updated_at: datetime


class ChapterVersionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    chapter_id: int
    version_kind: str
    version_no: int
    content: str
    summary: str | None
    score: int | None
    notes: dict[str, Any] | None
    created_at: datetime
