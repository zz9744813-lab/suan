"""P7: Genre-Prompt mapping + snapshot schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


# ============================================================
# GenrePromptMapping
# ============================================================
class GenrePromptMappingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    agent_role_key: str
    genre: str
    prompt_template_id: int
    priority: int
    sort_order: int
    created_at: datetime
    updated_at: datetime


class GenrePromptBindRequest(BaseModel):
    agent_role_key: str
    genre: str  # "" = generic fallback
    prompt_template_id: int
    priority: int = 0


class GenrePromptUnbindRequest(BaseModel):
    agent_role_key: str
    genre: str
    prompt_template_id: int


class GenrePromptReorderItem(BaseModel):
    id: int
    sort_order: int


class GenrePromptReorderRequest(BaseModel):
    items: list[GenrePromptReorderItem]


# ============================================================
# Matrix cell — one (agent_role_key × genre) cell
# ============================================================
class MatrixCell(BaseModel):
    agent_role_key: str
    genre: str
    prompt_template_id: int | None = None
    template_key: str | None = None
    template_name: str | None = None
    priority: int = 0
    sort_order: int = 0
    # visual hint
    state: str = "empty"  # "bound" | "fallback" | "empty"


class GenrePromptMatrixResponse(BaseModel):
    genres: list[str]
    agent_role_keys: list[str]
    cells: list[MatrixCell]


# ============================================================
# ProjectPromptSnapshot (traceability)
# ============================================================
class PromptSnapshotRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    chapter_id: int | None
    chapter_version_id: int | None
    trigger: str
    snapshot_data: dict[str, Any]
    created_at: datetime


class PromptSnapshotDetail(BaseModel):
    """Snapshot with chapter title resolved."""
    id: int
    chapter_id: int | None
    chapter_title: str | None
    trigger: str
    snapshot_data: dict[str, Any]
    created_at: datetime


# ============================================================
# Template create (manual add)
# ============================================================
class PromptTemplateCreate(BaseModel):
    template_key: str
    name: str
    category: str = "writing"
    role: str = "Draft"
    scope: str = "project"
    genre: str | None = None
    description: str | None = None
    allowed_inputs: list[str] = []
    forbidden_inputs: list[str] = []
    output_schema: str | None = None
    can_modify: list[str] = []
    cannot_modify: list[str] = []
    hard_rules: list[str] = []
    initial_body: str = ""


class TemplateUsageRead(BaseModel):
    template_id: int
    total_snapshots: int
    chapter_ids: list[int]
