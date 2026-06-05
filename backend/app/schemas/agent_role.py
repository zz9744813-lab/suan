"""P4: AgentRole / AgentModelBinding / AgentPromptBinding / AgentRun
Pydantic schemas. 跟 backend/app/models/agent_role.py 1:1 对应.

设计取舍:
  - AgentRoleRead / AgentRoleCreate / AgentRoleUpdate 跟表同构.
  - AgentRoleMatrixItem 是一行矩阵要的全部数据 (角色 + 绑定 +
    最新 run 状态) — 角色矩阵端点 /api/agent-roles/matrix 一次返回.
  - AgentRunRead / AgentRunEventRead 是 run 历史 / 实时日志.
  - AgentModelBindingUpdate 跟 spec §9.3 的请求 1:1.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


# ============================================================
# AgentRole (P4 §8.1)
# ============================================================
class AgentRoleBase(BaseModel):
    key: str
    display_name: str
    description: str | None = None
    # 6 类: writing / study / memory / discussion / review / custom
    # P6 新增 review (5 个模拟读者 Agent 共享)
    category: Literal["writing", "study", "memory", "discussion", "review", "custom"] = "custom"
    avatar_style: str | None = None
    enabled: bool = True
    visible_in_matrix: bool = True
    run_mode: Literal["manual", "pipeline", "scheduled", "event"] = "pipeline"
    pipeline_stage: str | None = None
    timeout_seconds: int = 120
    max_retries: int = 2
    concurrency_limit: int = 1
    cost_limit_usd: float | None = None


class AgentRoleCreate(AgentRoleBase):
    """POST /api/agent-roles"""
    pass


class AgentRoleUpdate(BaseModel):
    """PUT /api/agent-roles/{id} — 允许部分更新"""
    display_name: str | None = None
    description: str | None = None
    category: Literal["writing", "study", "memory", "discussion", "custom"] | None = None
    avatar_style: str | None = None
    enabled: bool | None = None
    visible_in_matrix: bool | None = None
    run_mode: Literal["manual", "pipeline", "scheduled", "event"] | None = None
    pipeline_stage: str | None = None
    timeout_seconds: int | None = None
    max_retries: int | None = None
    concurrency_limit: int | None = None
    cost_limit_usd: float | None = None


class AgentRoleRead(AgentRoleBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime


# ============================================================
# AgentModelBinding (P4 §8.2) — 角色绑的 provider/model
# ============================================================
class AgentModelBindingRead(BaseModel):
    # Pydantic v2 namespace conflict fix
    model_config = ConfigDict(from_attributes=True, protected_namespaces=())

    id: int
    agent_role_id: int
    provider_id: int | None
    model_name: str | None
    fallback_provider_id: int | None
    fallback_model_name: str | None
    temperature: float | None
    max_tokens: int | None
    extra_body: dict[str, Any] | None = None
    # ── P0-Model-Failover 新增字段 ──
    selection_mode: str = "auto"
    auto_strategy: str = "quality_first"
    candidate_provider_ids: list[int] | None = None
    candidate_models_json: list[dict[str, Any]] | None = None
    fallback_candidates_json: list[dict[str, Any]] | None = None
    allow_auto_fallback: bool = True
    failure_threshold: int = 2
    cooldown_seconds: int = 300
    locked_reason: str | None = None
    last_selected_provider_id: int | None = None
    last_selected_model_name: str | None = None
    last_selection_reason: str | None = None
    last_selection_score: float | None = None
    last_selection_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class AgentModelBindingUpdate(BaseModel):
    """PUT /api/agent-roles/{id}/model-binding — 一次写完整个绑定
    (跟 spec §9.3 请求一致). P0-Model-Config added locked support."""
    model_config = ConfigDict(protected_namespaces=())

    provider_id: int | None = None
    model_name: str | None = None
    fallback_provider_id: int | None = None
    fallback_model_name: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    extra_body: dict[str, Any] | None = None
    # ── P0-Model-Failover 旧字段 (保留兼容) ──
    selection_mode: Literal["auto", "manual", "manual_with_fallback"] | None = None
    auto_strategy: Literal[
        "quality_first", "cost_first", "speed_first",
        "long_context_first", "json_stable_first",
    ] | None = None
    candidate_provider_ids: list[int] | None = None
    candidate_models_json: list[dict[str, Any]] | None = None
    fallback_candidates_json: list[dict[str, Any]] | None = None
    allow_auto_fallback: bool | None = None
    failure_threshold: int | None = None
    cooldown_seconds: int | None = None
    locked_reason: str | None = None  # deprecated, use lock_reason
    # ── P0-Model-Config: locked mode 新字段 ──
    binding_mode: Literal["auto", "manual_with_fallback", "locked"] | None = None
    locked_provider_id: int | None = None
    locked_model_name: str | None = None
    lock_reason: str | None = None
    locked_by_user: bool | None = None
    allow_fallback: bool | None = None
    allow_auto_switch: bool | None = None
    updated_by: str | None = None


# ============================================================
# AgentPromptBinding (P4 §8.3)
# ============================================================
class AgentPromptBindingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    agent_role_id: int
    system_prompt_template_id: int | None
    task_prompt_template_id: int | None
    output_schema: dict[str, Any] | None
    strict_json: bool
    evidence_required: bool
    created_at: datetime
    updated_at: datetime


class AgentPromptBindingUpdate(BaseModel):
    """PUT /api/agent-roles/{id}/prompt-binding"""
    system_prompt_template_id: int | None = None
    task_prompt_template_id: int | None = None
    output_schema: dict[str, Any] | None = None
    strict_json: bool | None = None
    evidence_required: bool | None = None


# ============================================================
# AgentRun (P4 §8.4)
# ============================================================
class AgentRunRead(BaseModel):
    # Pydantic v2 namespace conflict fix
    model_config = ConfigDict(from_attributes=True, protected_namespaces=())

    id: int
    agent_role_id: int
    project_id: int | None
    task_id: int | None
    agent_step_id: int | None
    run_type: str
    # idle / queued / running / waiting / succeeded / failed / disabled
    status: str
    current_task: str | None
    progress: float
    provider_id: int | None
    model_name: str | None
    input_tokens: int
    output_tokens: int
    cost_usd: float
    elapsed_ms: int | None
    input_summary: str | None
    output_summary: str | None
    error_message: str | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime


# ============================================================
# AgentRunEvent (P4 §8.5)
# ============================================================
class AgentRunEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    agent_run_id: int
    event_type: str
    message: str
    payload: dict[str, Any] | None
    created_at: datetime


# ============================================================
# 角色矩阵 (P4 §9.4 /api/agent-roles/matrix) — 一次返回矩阵所有行
# ============================================================
class AgentRoleMatrixItem(BaseModel):
    """One row of the role binding matrix. 把 AgentRole +
    AgentModelBinding + 最新 AgentRun 拼一起, 前端不用自己 join.

    P4 §4 状态枚举 (中英): 待命/排队/运行中/等待上游/完成/失败/禁用
    """
    # Pydantic v2 protected_namespaces — `model_name` 跟 pydantic
    # 内部 model_* namespace 冲突, 关掉.
    model_config = ConfigDict(from_attributes=True, protected_namespaces=())
    role: AgentRoleRead
    binding: AgentModelBindingRead | None = None
    prompt_binding: AgentPromptBindingRead | None = None
    # 派生字段
    status: str = "idle"
    status_label: str = "待命"
    current_task: str | None = None
    progress: float = 0.0
    provider_name: str | None = None
    model_name: str | None = None
    last_run_id: int | None = None
    last_run_at: datetime | None = None
    last_error: str | None = None
    total_runs: int = 0
    # 最近 10 次运行的统计
    recent_runs: list[AgentRunRead] = Field(default_factory=list)
    recent_events: list[AgentRunEventRead] = Field(default_factory=list)


class AgentRoleMatrixResponse(BaseModel):
    items: list[AgentRoleMatrixItem]
    # 5 个 category 的计数 (P4 §4 折叠)
    section_counts: dict[str, int] = Field(default_factory=dict)
