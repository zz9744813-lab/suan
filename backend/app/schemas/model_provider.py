"""Model provider / role schemas."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ModelProviderCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=80)
    base_url: str = Field(..., min_length=1)
    api_key: str = Field(..., min_length=1)
    default_model: str = ""
    enabled: bool = True
    extra: dict | None = None


class ModelProviderRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, protected_namespaces=())

    id: int
    name: str
    base_url: str
    api_key: str  # returned in full; UI masks it
    default_model: str
    model_list: list[str]
    enabled: bool
    last_test_status: str | None
    last_test_message: str | None
    last_test_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ModelProviderTestResult(BaseModel):
    ok: bool
    message: str
    models: list[str] = Field(default_factory=list)
    suggestion: str | None = None
    latency_ms: int | None = None


class ModelRoleAssignmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    role: str
    provider_id: int
    provider_name: str | None = None
    model: str
    temperature: float
    max_tokens: int
    notes: str | None


class ModelRoleAssignmentUpdate(BaseModel):
    provider_id: int
    model: str
    temperature: float = 0.8
    max_tokens: int = 2048
    notes: str | None = None
