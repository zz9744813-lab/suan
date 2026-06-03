"""ChiefAgent schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ChiefAgentSessionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    project_id: int | None
    page_context: str | None
    status: str
    created_at: datetime
    updated_at: datetime


class ChiefAgentMessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    session_id: int
    role: str
    content: str
    actions: list[dict[str, Any]]
    thinking: str | None
    tokens_in: int
    tokens_out: int
    cost_usd: float
    created_at: datetime


class ChiefAgentChatRequest(BaseModel):
    session_id: int | None = None
    project_id: int | None = None
    page_context: str | None = None
    message: str = Field(..., min_length=1)


class ChiefAgentAction(BaseModel):
    action_id: str
    type: str  # create_project / generate_bible / generate_outline / start_worker ...
    label: str
    description: str
    params: dict[str, Any] = Field(default_factory=dict)
    requires_confirm: bool = True
