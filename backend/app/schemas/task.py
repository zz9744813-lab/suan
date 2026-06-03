"""Task / step / worker schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

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
    # P0-3 fix: the ORM has these columns but the read schema never
    # exported them, so the chapter-detail UI rendered
    # ``模板 #undefined vundefined`` for every step.
    prompt_template_id: int | None
    prompt_version: int | None
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


# ----- Round 3 / P1-FUNC-1: task diagnosis -----

# Pipeline order (matches ChapterPipeline). The UI uses this to show
# a 1-1 mapping between ``step_name`` and a human-friendly label, and
# to compute the list of steps that were *skipped* because an earlier
# one failed.
PIPELINE_STEP_ORDER: tuple[str, ...] = (
    "context_compile",
    "plan",
    "draft",
    "review",
    "rewrite",
    "continuity",
    "memory_update",
    "learning",
)

STEP_LABELS: dict[str, str] = {
    "context_compile": "上下文组装",
    "plan": "Planner 大纲",
    "draft": "Drafter 写稿",
    "review": "Critic 评审",
    "rewrite": "Rewriter 改稿",
    "continuity": "Continuity 连贯性",
    "memory_update": "MemoryUpdate 记忆",
    "learning": "Learning 反思",
}


class TaskDiagnosisStep(BaseModel):
    """One row in the AgentStepRail / diagnosis timeline."""
    step_name: str
    label: str
    status: str  # pending / running / succeeded / failed / skipped
    agent_name: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_ms: int = 0
    cost_usd: float = 0.0
    score: int | None = None  # critic score, if any
    error_message: str | None = None


class TaskDiagnosisSuggestion(BaseModel):
    """An actionable next step surfaced in the FailureDiagnosisCard."""
    type: Literal[
        "safe_retry",          # retry the failed step only
        "from_failed_step",    # retry everything from the failed step
        "continue_with_fallback",  # use fallback critic report, continue
        "switch_model",        # edit role binding, then retry
        "view_step",           # jump to the chapter's step timeline
        "open_models",         # jump to the model config page
    ]
    label: str
    description: str
    risk: Literal["low", "medium", "high"] = "low"
    # ``params`` carries whatever the action needs to round-trip to
    # the backend (e.g. ``task_id`` for the retry endpoint).
    params: dict[str, Any] = Field(default_factory=dict)


class TaskDiagnosisRead(BaseModel):
    """Structured failure analysis. P1-FUNC-1 in the spec."""
    task_id: int
    project_id: int
    chapter_id: int | None
    task_type: str
    status: str
    error_type: str  # e.g. "JSON_PARSE_FAILED" / "TIMEOUT" / ...
    error_message: str
    failed_agent: str | None
    failed_step: str | None
    impact: list[str]            # human-readable list of skipped steps
    suggestions: list[TaskDiagnosisSuggestion]
    raw_output_preview: str | None
    prompt_preview: str | None
    steps: list[TaskDiagnosisStep]
    retry_count: int


class TaskRetryRequest(BaseModel):
    """Body for ``POST /api/tasks/{task_id}/retry`` (P1-FUNC-2)."""
    mode: Literal["full", "from_failed_step", "critic_only", "continue_with_fallback"] = "full"
    from_step: str | None = None  # required when mode == "from_failed_step"
    reuse_previous_outputs: bool = True
