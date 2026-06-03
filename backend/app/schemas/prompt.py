"""Prompt template schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class PromptTemplateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    template_key: str
    name: str
    category: str
    role: str
    scope: str
    genre: str | None
    description: str | None
    allowed_inputs: list[str]
    forbidden_inputs: list[str]
    output_schema: str | None
    can_modify: list[str]
    cannot_modify: list[str]
    hard_rules: list[str]
    active_version_id: int | None
    updated_at: datetime


class PromptVersionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    template_id: int
    version: int
    body: str
    status: str
    change_note: str | None
    test_pass_rate: float
    avg_score_delta: float
    usage_count: int
    created_at: datetime


class PromptVersionUpdate(BaseModel):
    body: str
    change_note: str | None = None
    activate: bool = False
