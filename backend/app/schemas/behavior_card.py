"""Behavior Card Pydantic schemas — P8 behavior-card-knowledge-base."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Tag
# ---------------------------------------------------------------------------
class CardTagCreate(BaseModel):
    tag_type: str = Field(..., max_length=40)
    tag_name: str = Field(..., max_length=80)
    weight: float = Field(default=1.0)


class CardTagRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    tag_type: str
    tag_name: str
    weight: float


# ---------------------------------------------------------------------------
# Technique
# ---------------------------------------------------------------------------
class CardTechniqueCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=160)
    content: str = Field(..., min_length=1)
    example: str | None = None
    priority: int = Field(default=0)


class CardTechniqueUpdate(BaseModel):
    title: str | None = None
    content: str | None = None
    example: str | None = None
    priority: int | None = None


class CardTechniqueRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    title: str
    content: str
    example: str | None
    priority: int


# ---------------------------------------------------------------------------
# Source
# ---------------------------------------------------------------------------
class CardSourceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    book_id: int | None
    book_title: str | None
    chapter_title: str | None
    source_type: str
    source_excerpt: str | None
    extracted_summary: str | None
    confidence: float


# ---------------------------------------------------------------------------
# Usage Log
# ---------------------------------------------------------------------------
class CardUsageLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    project_id: int | None
    chapter_id: int | None
    task_id: int | None
    agent_role: str | None
    usage_type: str | None
    prompt_excerpt: str | None
    output_excerpt: str | None
    feedback_score: float | None
    created_at: datetime


# ---------------------------------------------------------------------------
# Category
# ---------------------------------------------------------------------------
class BehaviorCategoryCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    slug: str = Field(..., min_length=1, max_length=120)
    description: str | None = None
    icon: str | None = None
    sort_order: int = Field(default=0)


class BehaviorCategoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    slug: str
    description: str | None
    icon: str | None
    sort_order: int
    is_collapsed: bool
    card_count: int = 0
    created_at: datetime
    updated_at: datetime


class BehaviorCategoryCollapseRequest(BaseModel):
    is_collapsed: bool


# ---------------------------------------------------------------------------
# Behavior Card — Summary (for list views)
# ---------------------------------------------------------------------------
class BehaviorCardSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    category_id: int | None
    name: str
    role_type: str | None
    status: str
    avatar_symbol: str | None
    color_theme: str | None
    summary: str | None
    behavior_chain: str | None
    fit_score: float
    source_count: int
    technique_count: int
    usage_count: int
    sort_order: int
    last_used_at: datetime | None
    updated_at: datetime
    # nested
    tags: list[CardTagRead] = []


# ---------------------------------------------------------------------------
# Behavior Card — Detail (for right drawer)
# ---------------------------------------------------------------------------
class BehaviorCardDetail(BehaviorCardSummary):
    typical_behavior: str | None
    emotion_chain: str | None
    dialogue_style: str | None
    suitable_scenes: str | None
    unsuitable_scenes: str | None
    injection_hint: str | None
    stability_score: float
    dialogue_score: float
    generalization_score: float
    created_at: datetime
    # nested
    category: BehaviorCategoryRead | None = None
    techniques: list[CardTechniqueRead] = []
    sources: list[CardSourceRead] = []
    usage_logs: list[CardUsageLogRead] = []


# ---------------------------------------------------------------------------
# Behavior Card — Create / Update
# ---------------------------------------------------------------------------
class BehaviorCardCreate(BaseModel):
    category_id: int | None = None
    name: str = Field(..., min_length=1, max_length=160)
    role_type: str | None = None
    avatar_symbol: str | None = None
    color_theme: str | None = None
    summary: str | None = None
    typical_behavior: str | None = None
    emotion_chain: str | None = None
    behavior_chain: str | None = None
    dialogue_style: str | None = None
    suitable_scenes: str | None = None
    unsuitable_scenes: str | None = None
    injection_hint: str | None = None
    status: str = Field(default="ready")
    tags: list[CardTagCreate] = []
    techniques: list[CardTechniqueCreate] = []


class BehaviorCardUpdate(BaseModel):
    category_id: int | None = None
    name: str | None = None
    role_type: str | None = None
    avatar_symbol: str | None = None
    color_theme: str | None = None
    summary: str | None = None
    typical_behavior: str | None = None
    emotion_chain: str | None = None
    behavior_chain: str | None = None
    dialogue_style: str | None = None
    suitable_scenes: str | None = None
    unsuitable_scenes: str | None = None
    injection_hint: str | None = None
    status: str | None = None
    fit_score: float | None = None
    stability_score: float | None = None
    dialogue_score: float | None = None
    generalization_score: float | None = None
    # replace tags / techniques wholesale
    tags: list[CardTagCreate] | None = None
    techniques: list[CardTechniqueCreate] | None = None


class BehaviorCardMoveRequest(BaseModel):
    target_category_id: int
    sort_order: int | None = None


class BehaviorCardListResponse(BaseModel):
    items: list[BehaviorCardSummary]
    total: int
