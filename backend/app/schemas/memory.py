"""Memory schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


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


MemoryCharacterRead.model_rebuild()
