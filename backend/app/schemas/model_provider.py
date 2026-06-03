"""Model provider / role schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


def mask_api_key(key: str | None) -> str:
    """Return a UI-safe version of an API key.

    P0-6 fix: previously the read schema returned the full key and
    relied on the UI to mask it, but the key was still visible in the
    browser's network tab. We now return only a short prefix/suffix
    preview, plus a boolean so the UI can show "(not set)" when no
    key has been configured.
    """
    if not key:
        return ""
    if len(key) <= 8:
        return "****"
    return f"{key[:4]}…{key[-4:]}"


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
    # P0-6 fix: never return the full key. ``api_key`` is the masked
    # preview (``ab12…wxyz``) and ``has_api_key`` tells the editor
    # whether to keep the existing value when the user submits an
    # empty input.
    api_key: str = ""
    has_api_key: bool = False
    default_model: str
    model_list: list[str]
    enabled: bool
    last_test_status: str | None
    last_test_message: str | None
    last_test_at: datetime | None
    # P0-MODEL-3: lightweight per-model health probe.
    last_health_status: str | None = None
    last_health_message: str | None = None
    last_health_latency_ms: int | None = None
    last_health_model: str | None = None
    last_health_at: datetime | None = None
    extra: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_orm_masked(cls, obj) -> "ModelProviderRead":
        """Build the read schema from a ModelProvider row, masking the key.

        Use this in routers instead of ``ModelProviderRead.model_validate``
        when reading from the DB, so the key is never serialised in full.
        """
        return cls(
            id=obj.id,
            name=obj.name,
            base_url=obj.base_url,
            api_key=mask_api_key(obj.api_key),
            has_api_key=bool(obj.api_key),
            default_model=obj.default_model,
            model_list=list(obj.model_list or []),
            enabled=obj.enabled,
            last_test_status=obj.last_test_status,
            last_test_message=obj.last_test_message,
            last_test_at=obj.last_test_at,
            last_health_status=obj.last_health_status,
            last_health_message=obj.last_health_message,
            last_health_latency_ms=obj.last_health_latency_ms,
            last_health_model=obj.last_health_model,
            last_health_at=obj.last_health_at,
            extra=obj.extra,
            created_at=obj.created_at,
            updated_at=obj.updated_at,
        )


class ModelProviderTestResult(BaseModel):
    ok: bool
    message: str
    models: list[str] = Field(default_factory=list)
    suggestion: str | None = None
    latency_ms: int | None = None


# P0-MODEL-3: lightweight per-model health probe.
# The status field is a friendly enum the UI can map straight to a
# colour-coded pill (green / yellow / red). The endpoint distinguishes
# "model replied but slow" (``degraded``) from a real failure
# (``unreachable`` / ``auth_failed`` / ``model_missing``) so the
# dashboard never shows a red bar for a slow-but-healthy provider.
HealthStatus = Literal[
    "healthy",        # replied within 5s
    "degraded",       # replied but > 5s
    "unreachable",    # TCP / DNS / HTTP 5xx
    "auth_failed",    # 401 / 403
    "model_missing",  # 404 on the model id
    "unknown_error",  # anything else
]


class ModelHealthCheckResult(BaseModel):
    ok: bool
    status: HealthStatus
    message: str
    suggestion: str | None = None
    model: str
    latency_ms: int
    checked_at: datetime


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


class ModelProviderUpdate(BaseModel):
    """PATCH-style update for a Provider.

    P0-6 fix: ``api_key`` is optional and may be empty/missing. The
    router treats an empty string as "leave the existing key in place"
    — otherwise editing any other field would silently wipe the key.

    ``base_url`` and ``name`` stay required to match the create schema
    (you can re-send the same value if you don't want to change them).
    """
    name: str = Field(..., min_length=1, max_length=80)
    base_url: str = Field(..., min_length=1)
    api_key: str = ""  # empty => keep existing
    default_model: str = ""
    enabled: bool = True
    extra: dict | None = None
