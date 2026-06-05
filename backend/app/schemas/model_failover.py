"""P0-Model-Failover: ModelRuntimeStat / ModelCallEvent / 选模预览 / 自动配置 schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


# ============================================================
# ModelRuntimeStat
# ============================================================
class ModelRuntimeStatRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, protected_namespaces=())

    id: int
    provider_id: int
    model_name: str
    agent_role_key: str | None
    window: str
    total_calls: int
    success_calls: int
    failed_calls: int
    json_parse_failures: int
    empty_response_failures: int
    timeout_failures: int
    auth_failures: int
    rate_limit_failures: int
    avg_latency_ms: int | None
    p95_latency_ms: int | None
    input_tokens: int
    output_tokens: int
    cost_usd: float
    quality_score: float | None
    updated_at: datetime


# ============================================================
# ModelCallEvent
# ============================================================
class ModelCallEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, protected_namespaces=())

    id: int
    provider_id: int | None
    model_name: str | None
    agent_role_key: str | None
    project_id: int | None
    task_id: int | None
    agent_step_id: int | None
    selection_mode: str | None
    selection_score: float | None
    selection_reason: str | None
    status: str
    failure_type: str | None
    failure_message: str | None
    latency_ms: int | None
    input_tokens: int
    output_tokens: int
    cost_usd: float
    created_at: datetime


# ============================================================
# 选模预览 (§8.2)
# ============================================================
class ModelCandidateItem(BaseModel):
    """一个候选模型的评分详情."""
    provider_id: int
    provider_name: str
    model_name: str
    score: float
    health: float | None = None
    success_rate: float | None = None
    latency_ms: int | None = None
    cost_score: float | None = None
    risk: list[str] = Field(default_factory=list)


class PreviewSelectionRequest(BaseModel):
    """POST /api/agent-roles/{role_id}/model-binding/preview-selection"""
    selection_mode: Literal["auto", "manual", "manual_with_fallback"] = "auto"
    auto_strategy: Literal[
        "quality_first", "cost_first", "speed_first",
        "long_context_first", "json_stable_first",
    ] = "quality_first"
    candidate_provider_ids: list[int] | None = None
    agent_role_key: str | None = None


class PreviewSelectionResponse(BaseModel):
    selected: ModelCandidateItem
    candidates: list[ModelCandidateItem] = Field(default_factory=list)


# ============================================================
# 一键自动配置 (§8.3)
# ============================================================
class AutoConfigureRequest(BaseModel):
    """POST /api/agent-roles/auto-configure"""
    project_id: int | None = None
    scope: Literal["all", "auto_only"] = "all"
    strategy: Literal[
        "quality_first", "cost_first", "speed_first",
        "long_context_first", "json_stable_first",
    ] = "quality_first"
    overwrite_manual: bool = False
    include_disabled: bool = False


class AutoConfigureItem(BaseModel):
    agent_role_key: str
    selection_mode: str
    provider: str | None
    model: str | None
    score: float | None
    reason: str | None


class AutoConfigureResponse(BaseModel):
    updated: int = 0
    skipped_manual: int = 0
    failed: int = 0
    items: list[AutoConfigureItem] = Field(default_factory=list)


# ============================================================
# Provider 健康全量探针 (§8.4)
# ============================================================
class ProviderHealthFullModelItem(BaseModel):
    model: str
    available: bool
    json_score: float | None = None
    long_output_score: float | None = None
    speed_score: float | None = None
    recommended_roles: list[str] = Field(default_factory=list)


class ProviderHealthFullResponse(BaseModel):
    provider_id: int
    status: str
    health_score: float
    latency_ms: int | None
    models: list[ProviderHealthFullModelItem] = Field(default_factory=list)


# ============================================================
# 熔断解除 (§8.5)
# ============================================================
class CircuitResetResponse(BaseModel):
    ok: bool
    provider_id: int
    circuit_state: str
    message: str | None = None
