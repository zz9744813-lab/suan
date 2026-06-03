"""Memory schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class MemoryCharacterRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    name: str
    aliases: list[str]
    role: str
    tags: list[str]
    base_profile: dict[str, Any]
    latest_state: "MemoryCharacterStateRead | None" = None


class MemoryCharacterStateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    character_id: int
    project_id: int
    chapter_no: int
    current_location: str | None
    current_faction: str | None
    current_goal: str | None
    injury_state: str | None
    emotion_state: str | None
    secrets: list[str]
    misunderstandings: list[str]
    relationships: dict[str, Any]
    owned_items: list[str]
    abilities: list[str]
    last_seen_chapter: int | None


class MemoryForeshadowRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    name: str
    summary: str
    planted_chapter: int | None
    expected_payoff_chapter: int | None
    actual_payoff_chapter: int | None
    status: str
    importance: float
    related_characters: list[str]
    related_items: list[str]
    related_main_plot: str | None


class MemoryHardFactRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    category: str
    fact: str
    source_chapter: int | None
    created_at: datetime


# ---- Write-side schemas (added Round 9) ----

class MemoryCharacterCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    aliases: list[str] = Field(default_factory=list)
    role: str = Field(default="support", max_length=40)
    tags: list[str] = Field(default_factory=list)
    base_profile: dict[str, Any] = Field(default_factory=dict)


class MemoryCharacterUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    aliases: list[str] | None = None
    role: str | None = None
    tags: list[str] | None = None
    base_profile: dict[str, Any] | None = None


class MemoryForeshadowCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    summary: str = Field(default="", max_length=2000)
    planted_chapter: int | None = None
    expected_payoff_chapter: int | None = None
    importance: float = Field(default=0.5, ge=0.0, le=1.0)
    related_characters: list[str] = Field(default_factory=list)
    related_items: list[str] = Field(default_factory=list)
    related_main_plot: str | None = None


class MemoryForeshadowUpdate(BaseModel):
    """Patch fields. Special: status="paid_off" + actual_payoff_chapter
    should be set together; the router accepts them independently for
    flexibility."""
    name: str | None = None
    summary: str | None = None
    planted_chapter: int | None = None
    expected_payoff_chapter: int | None = None
    actual_payoff_chapter: int | None = None
    status: str | None = None  # active / paid_off / dropped
    importance: float | None = Field(default=None, ge=0.0, le=1.0)
    related_characters: list[str] | None = None
    related_items: list[str] | None = None
    related_main_plot: str | None = None


class MemoryHardFactCreate(BaseModel):
    category: str = Field(default="setting", max_length=40)
    fact: str = Field(..., min_length=1, max_length=2000)
    source_chapter: int | None = None


MemoryCharacterRead.model_rebuild()
