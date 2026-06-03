"""Task / step / worker schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AgentTaskCreate(BaseModel):
    project_id: int
    chapter_id: int | None = None
    task_type: str = "chapter_pipeline"
    priority: int = 100
    payload: dict[str, Any] = Field(default_factory=dict)
    max_retries: int = 3


class AgentTaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    chapter_id: int | None
    task_type: str
    status: str
    priority: int
    payload: dict[str, Any]
    error: str | None
    retry_count: int
    cost_usd: float
    input_tokens: int
    output_tokens: int
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime


class AgentStepRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, protected_namespaces=())

    id: int
    task_id: int
    project_id: int
    chapter_id: int | None
    agent_name: str
    step_name: str
    status: str
    input_prompt: str | None
    raw_output: str | None
    parsed_output: dict[str, Any] | None
    model_name: str | None
    provider_name: str | None
    input_tokens: int
    output_tokens: int
    cost_usd: float
    duration_ms: int
    error_message: str | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime


class AgentEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int | None
    chapter_id: int | None
    task_id: int | None
    event_type: str
    level: str
    message: str
    data: dict[str, Any] | None
    created_at: datetime


class WorkerStatusRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    state: str
    current_task_id: int | None
    last_heartbeat_at: datetime | None
    consecutive_failures: int
    today_words: int
    today_cost_usd: float
    last_error: str | None
    updated_at: datetime


class WorkerPolicyUpdate(BaseModel):
    daily_word_goal: int | None = None
    daily_budget_usd: float | None = None
    pass_score: int | None = None
    max_rewrite_rounds: int | None = None
    max_retry_per_task: int | None = None
    consecutive_fail_stop: int | None = None
    auto_continue: bool | None = None
    discussion_policy: str | None = None
    max_discussion_per_day: int | None = None
    max_cost_per_discussion: float | None = None


class WorkerPolicyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    daily_word_goal: int
    daily_budget_usd: float
    pass_score: int
    max_rewrite_rounds: int
    max_retry_per_task: int
    consecutive_fail_stop: int
    auto_continue: bool
    discussion_policy: str
    max_discussion_per_day: int
    max_cost_per_discussion: float
