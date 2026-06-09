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
    api_key: str = ""  # optional: can add later
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
    # P15 / P0-HEALTH-1: per-test detail + role recommendations
    # (single JSON blob so the role matrix can colour-code bindings
    # without re-running the probe on every page load).
    last_health_full: dict[str, Any] | None = None
    extra: dict[str, Any] | None = None
    # P0-MODEL-FAILOVER: circuit-breaker + runtime stats.
    health_score: float | None = None
    success_rate_1h: float | None = None
    success_rate_24h: float | None = None
    avg_latency_ms: int | None = None
    consecutive_failures: int = 0
    consecutive_successes: int = 0
    circuit_state: str = "closed"
    circuit_open_until: datetime | None = None
    last_failure_type: str | None = None
    last_failure_message: str | None = None
    last_success_at: datetime | None = None
    daily_cost_usd: float = 0.0
    daily_request_count: int = 0
    daily_token_count: int = 0
    last_reset_date: str | None = None
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
            # P15 / P0-HEALTH-1: pass through the per-test detail.
            last_health_full=obj.last_health_full,
            extra=obj.extra,
            # P0-MODEL-FAILOVER: circuit-breaker + runtime stats.
            health_score=obj.health_score,
            success_rate_1h=obj.success_rate_1h,
            success_rate_24h=obj.success_rate_24h,
            avg_latency_ms=obj.avg_latency_ms,
            consecutive_failures=obj.consecutive_failures,
            consecutive_successes=obj.consecutive_successes,
            circuit_state=obj.circuit_state or "closed",
            circuit_open_until=obj.circuit_open_until,
            last_failure_type=obj.last_failure_type,
            last_failure_message=obj.last_failure_message,
            last_success_at=obj.last_success_at,
            daily_cost_usd=obj.daily_cost_usd or 0.0,
            daily_request_count=obj.daily_request_count or 0,
            daily_token_count=obj.daily_token_count or 0,
            last_reset_date=obj.last_reset_date,
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
    "healthy",        # all probed tests passed
    "degraded",       # some tests passed, some failed / warned
    "unreachable",    # TCP / DNS / HTTP 5xx
    "auth_failed",    # 401 / 403
    "model_missing",  # 404 on the model id
    "unknown_error",  # anything else
]


# P15 / P0-HEALTH-1: per-test health item. The probe runs N tests
# (short_chat, json_output, critic_schema, long_text) and reports each
# independently. The top-level ``status`` is derived from the items
# below so the UI can drill in.
HealthCheckItemName = Literal[
    "short_chat",     # can the model reply to a 1-token ping? (ping)
    "json_output",    # does the model output strict JSON without markdown?
    "critic_schema",  # does the model return the Critic JSON schema?
    "long_text",      # can the model output ≥ 1000 chars of Chinese prose?
]

HealthCheckItemStatus = Literal[
    "passed",
    "failed",
    "warning",
    "skipped",
]


class ModelHealthCheckItem(BaseModel):
    """One probe in a multi-test health check.

    P15 / P0-HEALTH-1: each item carries its own latency so the UI can
    show the slow-but-passed cases in a different colour from
    fast-and-passed. ``raw_preview`` is a truncated view of the raw
    model output for the items that need a human to look (critic
    schema failures, JSON wrapped in markdown, ...).
    """
    name: HealthCheckItemName
    status: HealthCheckItemStatus
    latency_ms: int
    message: str
    suggestion: str | None = None
    raw_preview: str | None = None


class ModelHealthCheckResult(BaseModel):
    """Aggregate health check result.

    Backward-compatible with R11 (the original ping-only probe):
    ``status`` / ``message`` / ``suggestion`` / ``latency_ms`` keep
    their old semantics so the role-matrix "健康" cell keeps working
    without code changes there. The new fields are:
      - ``results``: per-test breakdown
      - ``score``: 0..100 (weighted average of test pass rates)
      - ``recommended_roles``: roles the model is suitable for, given
        its test results (e.g. a model that passed critic_schema is
        eligible for the ``Critic`` role; one that passed long_text
        is eligible for ``Draft`` / ``Rewrite``).
    """
    ok: bool
    status: HealthStatus
    message: str
    suggestion: str | None = None
    model: str
    latency_ms: int
    checked_at: datetime
    # P15 / P0-HEALTH-1: per-test detail.
    results: list[ModelHealthCheckItem] = Field(default_factory=list)
    score: int = 0
    # role -> list of "suitable" | "risky" | "unsuitable" reasons.
    recommended_roles: dict[str, str] = Field(default_factory=dict)


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

    ``name`` and ``base_url`` are optional to support partial updates
    from the frontend (e.g. changing just ``base_url`` without re-sending
    ``name``). None values are skipped by the router.
    """
    name: str | None = Field(default=None, min_length=1, max_length=80)
    base_url: str | None = Field(default=None, min_length=1)
    api_key: str = ""  # empty => keep existing
    default_model: str | None = None
    enabled: bool | None = None
    extra: dict | None = None


# P0-MODEL-7: lightweight 「试拉一下」 endpoint. The user is filling in
# the new-Provider form and wants a dropdown of models the provider
# exposes — but they haven't saved the row yet, so we can't reuse the
# /test endpoint (which needs a provider_id). This endpoint takes the
# raw base_url + api_key from the form, calls
# ``LLMClient.list_models`` directly, and returns the list. We
# deliberately do NOT touch the database: it's a stateless preview.
class ProviderPreviewModelsRequest(BaseModel):
    base_url: str = Field(..., min_length=1)
    api_key: str = ""  # mock:// URLs don't need a real key; some
    # providers (e.g. local llama.cpp) also allow empty keys.


class ProviderPreviewModelsResponse(BaseModel):
    ok: bool
    models: list[str] = Field(default_factory=list)
    message: str = ""
    suggestion: str | None = None
    latency_ms: int | None = None


# ---------------------------------------------------------------------------
# P-Delete-Preview: delete-preview payload
# ---------------------------------------------------------------------------
class ProviderRoleBindingImpact(BaseModel):
    """A role assignment that will be cascade-deleted with the provider.

    The UI shows each row so the operator can spot the binding they
    care about (e.g. "Draft -> stub" disappearing).
    """

    id: int
    role: str
    model: str


class ProviderCallEventImpact(BaseModel):
    """Summary of the call events that will lose their provider_id.

    The rows themselves are NOT deleted (they're an audit log); we
    just clear their ``provider_id`` via ``ON DELETE SET NULL``. The
    UI uses ``count`` and ``last_called_at`` to set expectations:
    "yes, the history stays, but the provider badge will be blank".
    """

    count: int
    last_called_at: datetime | None = None


class ProviderDisablePreview(BaseModel):
    provider_id: int
    provider_name: str
    enabled: bool
    affected_role_bindings: list[ProviderRoleBindingImpact] = Field(default_factory=list)
    active_call_events_count: int = 0
    summary: str
    danger_level: Literal["safe", "caution", "danger"]


class ProviderDeletePreview(BaseModel):
    """P-Delete-Preview: preflight summary for DELETE /providers/{id}.

    Returned by ``GET /providers/{id}/delete-preview`` so the UI can
    warn the operator before pulling the trigger. The intent is to
    surface cascade effects (which role bindings will disappear, how
    much call history will lose its provider badge) without
    preventing the delete — we picked "physical delete" in the design
    phase. The only block-worthy case is a not-found provider.
    """

    provider_id: int
    provider_name: str
    base_url: str
    will_cascade_role_bindings: list[ProviderRoleBindingImpact] = Field(
        default_factory=list,
    )
    will_cascade_call_events_count: int = 0
    last_call_event_at: datetime | None = None
    # P-Delete-Preview: human-readable rollup. The UI shows this in
    # the confirmation dialog as the body text, but a backend-side
    # summary keeps it consistent with any future CLI / API consumer.
    summary: str
    # P-Delete-Preview: danger level drives the dialog header colour
    # and the confirm-button style. ``safe`` = no role bindings and
    # no call history; ``caution`` = some history; ``danger`` =
    # currently bound to one or more roles.
    danger_level: Literal["safe", "caution", "danger"]
