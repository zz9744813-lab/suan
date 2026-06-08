from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

DomainKey = Literal["writing", "study", "feedback", "memory", "governance"]
DomainStatus = Literal["healthy", "warning", "blocked", "idle", "running"]
RiskSeverity = Literal["info", "warning", "critical"]
ActionSeverity = Literal["primary", "normal", "warning", "danger"]
Tone = Literal["neutral", "ok", "warning", "danger"]


class WorkbenchScope(BaseModel):
    mode: Literal["global", "project"]
    project_id: int | None = None
    project_name: str | None = None
    domain: DomainKey | None = None


class WorkbenchMetric(BaseModel):
    key: str
    label: str
    value: int | float | str | None = None
    unit: str | None = None
    tone: Tone = "neutral"


class WorkbenchRisk(BaseModel):
    key: str
    domain: DomainKey
    severity: RiskSeverity
    title: str
    summary: str
    entity_type: str | None = None
    entity_id: int | None = None
    project_id: int | None = None
    chapter_id: int | None = None
    task_id: int | None = None
    route: str | None = None
    created_at: datetime | None = None


class WorkbenchAction(BaseModel):
    key: str
    label: str
    domain: DomainKey
    severity: ActionSeverity = "normal"
    requires_confirm: bool = False
    description: str | None = None
    route: str | None = None
    method: Literal["GET", "POST", "PATCH", "PUT", "DELETE"] | None = None
    endpoint: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    disabled: bool = False
    disabled_reason: str | None = None


class WorkbenchDomainCard(BaseModel):
    key: DomainKey
    title: str
    status: DomainStatus
    summary: str
    metrics: list[WorkbenchMetric] = Field(default_factory=list)
    risks: list[WorkbenchRisk] = Field(default_factory=list)
    actions: list[WorkbenchAction] = Field(default_factory=list)
    route: str


class WorkbenchPrimaryTask(BaseModel):
    id: int | None = None
    domain: DomainKey | None = None
    title: str | None = None
    task_type: str | None = None
    task_kind: str | None = None
    status: str | None = None
    project_id: int | None = None
    chapter_id: int | None = None
    material_id: int | None = None
    run_id: int | None = None
    progress_current: int = 0
    progress_total: int = 0
    progress_percent: int | None = None
    current_step: str | None = None
    error: str | None = None
    route: str | None = None
    started_at: datetime | None = None


class WorkbenchRecentOutput(BaseModel):
    key: str
    domain: DomainKey
    title: str
    summary: str | None = None
    entity_type: str
    entity_id: int | None = None
    project_id: int | None = None
    chapter_id: int | None = None
    route: str | None = None
    created_at: datetime | None = None


class WorkbenchWorkerSummary(BaseModel):
    state: str
    loop_state: str | None = None
    current_task_id: int | None = None
    running_count: int = 0
    pending_count: int = 0
    failed_count: int = 0
    stale_running_tasks: int = 0
    last_heartbeat_at: datetime | None = None


class WorkbenchModelSummary(BaseModel):
    providers_total: int = 0
    providers_healthy: int = 0
    providers_degraded: int = 0
    providers_failed: int = 0
    recent_failures: int = 0
    slow_calls: int = 0
    cost_today_usd: float = 0.0


class WorkbenchOverviewRead(BaseModel):
    scope: WorkbenchScope
    top_stats: list[WorkbenchMetric]
    domains: list[WorkbenchDomainCard]
    primary_task: WorkbenchPrimaryTask | None = None
    risks: list[WorkbenchRisk] = Field(default_factory=list)
    recommended_actions: list[WorkbenchAction] = Field(default_factory=list)
    recent_outputs: list[WorkbenchRecentOutput] = Field(default_factory=list)
    worker: WorkbenchWorkerSummary
    model_health: WorkbenchModelSummary
    as_of: datetime
