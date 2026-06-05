"""P4: Agent Role / Model Binding / Prompt Binding / Run / Event 数据模型.

按 spec 05_P4_§8 的 5 张表设计, 跟旧 ModelRoleAssignment(简单
provider_id+role) 解耦 — AgentRole 是"一个工作角色"(Planner / Draft
/ Critic / ...), 通过 AgentModelBinding 绑模型, AgentPromptBinding
绑 prompt, AgentRun/AgentRunEvent 记实时状态.

跟旧 ModelRoleAssignment 的关系:
  - 旧表还保留 (兼容 R11), 旧 API /api/models/roles 继续工作.
  - 新表是 P4 的"角色绑定矩阵"主源. 一个 AgentRole 行会有 0..1 个
    AgentModelBinding + 0..1 个 AgentPromptBinding. 这套结构支持
    任意新增 Agent (custom), 不需要写新代码.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON, Boolean, Float, ForeignKey, Integer, String, Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def _utcnow() -> datetime:
    return datetime.utcnow()


# ============================================================
# AgentRole (P4 §8.1) — 一个工作角色
# ============================================================
class AgentRole(Base):
    """A working role. key 是稳定字符串 (planner / draft / critic /
    custom:foreshadow_inspector 等); display_name 是用户看的; category
    决定它在矩阵里落到哪个 section (writing / study / memory /
    discussion / custom); enabled 控制是否被 worker 调度; visible_in_matrix
    控制是否在角色绑定矩阵里出现 (advanced 角色可隐藏到"更多")。
    """

    __tablename__ = "agent_roles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(Text, default=None)
    # 5 类: writing / study / memory / discussion / custom
    category: Mapped[str] = mapped_column(String(40), index=True)
    # 头像样式 key (orb / robot / scribe / critic / memory_core /
    # study_core / discussion_core / custom). 前端按这个字符串挑 SVG.
    avatar_style: Mapped[str | None] = mapped_column(String(60), default=None)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    visible_in_matrix: Mapped[bool] = mapped_column(Boolean, default=True)
    # 调度: manual (手动触发) / pipeline (章节流水线里) / scheduled /
    # event (事件驱动)
    run_mode: Mapped[str] = mapped_column(String(20), default="pipeline")
    pipeline_stage: Mapped[str | None] = mapped_column(String(60), default=None)
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=120)
    max_retries: Mapped[int] = mapped_column(Integer, default=2)
    concurrency_limit: Mapped[int] = mapped_column(Integer, default=1)
    cost_limit_usd: Mapped[float | None] = mapped_column(Float, default=None)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=_utcnow, onupdate=_utcnow)


# ============================================================
# AgentModelBinding (P4 §8.2) — 角色绑定的 provider/model
# ============================================================
class AgentModelBinding(Base):
    """One-to-one with AgentRole. 一个角色当前绑哪个 provider+model,
    以及 fallback. 这里 follow ModelRoleAssignment 的字段, 但加
    temperature/max_tokens/extra_body 让角色有完整的"模型档案"。
    """

    __tablename__ = "agent_model_bindings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    agent_role_id: Mapped[int] = mapped_column(
        ForeignKey("agent_roles.id", ondelete="CASCADE"), unique=True, index=True,
    )
    provider_id: Mapped[int | None] = mapped_column(
        ForeignKey("model_providers.id", ondelete="SET NULL"), default=None,
    )
    model_name: Mapped[str | None] = mapped_column(String(200), default=None)
    fallback_provider_id: Mapped[int | None] = mapped_column(
        ForeignKey("model_providers.id", ondelete="SET NULL"), default=None,
    )
    fallback_model_name: Mapped[str | None] = mapped_column(String(200), default=None)
    temperature: Mapped[float | None] = mapped_column(Float, default=None)
    max_tokens: Mapped[int | None] = mapped_column(Integer, default=None)
    # 给 OpenAI-compatible 客户端透传的 extra_body (例如
    # step-3.7-flash 的 reasoning_effort=low).
    extra_body: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=None)

    # ── P0-Model-Failover: 自动选模 / 手动锁定 / 混合模式 ──
    # auto / manual / manual_with_fallback
    selection_mode: Mapped[str] = mapped_column(String(30), default="auto", index=True)
    # quality_first / cost_first / speed_first / long_context_first / json_stable_first
    auto_strategy: Mapped[str] = mapped_column(String(40), default="quality_first")
    # 自动模式可用 Provider 池；为空表示所有 enabled Provider
    candidate_provider_ids: Mapped[list[int] | None] = mapped_column(JSON, default=None)
    # 指定候选模型池 [{"provider_id":1,"model":"step-3.7-flash","weight":1.0}, ...]
    candidate_models_json: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, default=None)
    # 手动模式失败后的备用模型池
    fallback_candidates_json: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, default=None)
    # manual 模式下是否允许失效后自动切换
    allow_auto_fallback: Mapped[bool] = mapped_column(Boolean, default=True)
    # 连续失败多少次触发切换
    failure_threshold: Mapped[int] = mapped_column(Integer, default=2)
    # 主模型失败后冷却多久（秒）
    cooldown_seconds: Mapped[int] = mapped_column(Integer, default=300)
    # 用户为什么手动锁定，UI 显示用
    locked_reason: Mapped[str | None] = mapped_column(Text, default=None)
    # ── 最近一次自动选择结果 ──
    last_selected_provider_id: Mapped[int | None] = mapped_column(
        ForeignKey("model_providers.id", ondelete="SET NULL"), default=None,
    )
    last_selected_model_name: Mapped[str | None] = mapped_column(String(200), default=None)
    last_selection_reason: Mapped[str | None] = mapped_column(Text, default=None)
    last_selection_score: Mapped[float | None] = mapped_column(Float, default=None)
    last_selection_at: Mapped[datetime | None] = mapped_column(default=None)

    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=_utcnow, onupdate=_utcnow)


# ============================================================
# AgentPromptBinding (P4 §8.3) — 角色绑定的 prompt / output schema
# ============================================================
class AgentPromptBinding(Base):
    """One-to-one with AgentRole. system_prompt_template + task_prompt
    走 PromptTemplate 复用, output_schema 决定 strict_json 模式,
    evidence_required 控制 plan 阶段要不要证据回引.
    """

    __tablename__ = "agent_prompt_bindings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    agent_role_id: Mapped[int] = mapped_column(
        ForeignKey("agent_roles.id", ondelete="CASCADE"), unique=True, index=True,
    )
    system_prompt_template_id: Mapped[int | None] = mapped_column(
        ForeignKey("prompt_templates.id", ondelete="SET NULL"), default=None,
    )
    task_prompt_template_id: Mapped[int | None] = mapped_column(
        ForeignKey("prompt_templates.id", ondelete="SET NULL"), default=None,
    )
    output_schema: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=None)
    strict_json: Mapped[bool] = mapped_column(Boolean, default=True)
    evidence_required: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=_utcnow, onupdate=_utcnow)


# ============================================================
# AgentRun (P4 §8.4) — 角色的一次具体运行
# ============================================================
class AgentRun(Base):
    """One execution of a role. P4 这边跟现有 AgentTask/AgentStep 的
    关系:

      AgentTask (章节级) 1—N AgentStep (阶段级) 1—N AgentRun (本表)

    P4 不要求新建 worker — AgentRun 行是"最近一次跑"的快照, 字段
    status / progress / current_task 来自最新一条 AgentStep. 这样
    角色矩阵的"当前状态"完全是 DB-派生, 不需要 worker 主动 push.
    """

    __tablename__ = "agent_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    agent_role_id: Mapped[int] = mapped_column(
        ForeignKey("agent_roles.id", ondelete="CASCADE"), index=True,
    )
    project_id: Mapped[int | None] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"), default=None, index=True,
    )
    task_id: Mapped[int | None] = mapped_column(
        ForeignKey("agent_tasks.id", ondelete="SET NULL"), default=None, index=True,
    )
    agent_step_id: Mapped[int | None] = mapped_column(
        ForeignKey("agent_steps.id", ondelete="SET NULL"), default=None, index=True,
    )
    run_type: Mapped[str] = mapped_column(String(40), default="pipeline")
    # idle / queued / running / waiting / succeeded / failed / disabled
    status: Mapped[str] = mapped_column(String(20), default="idle", index=True)
    current_task: Mapped[str | None] = mapped_column(String(300), default=None)
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    provider_id: Mapped[int | None] = mapped_column(
        ForeignKey("model_providers.id", ondelete="SET NULL"), default=None,
    )
    model_name: Mapped[str | None] = mapped_column(String(200), default=None)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    elapsed_ms: Mapped[int | None] = mapped_column(Integer, default=None)
    input_summary: Mapped[str | None] = mapped_column(Text, default=None)
    output_summary: Mapped[str | None] = mapped_column(Text, default=None)
    error_message: Mapped[str | None] = mapped_column(Text, default=None)
    started_at: Mapped[datetime | None] = mapped_column(default=None)
    finished_at: Mapped[datetime | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow, index=True)


# ============================================================
# AgentRunEvent (P4 §8.5) — run 内的实时事件
# ============================================================
class AgentRunEvent(Base):
    """One event in an AgentRun. 9 event types per spec:
    queued / started / llm_request / llm_response / parsed / retry /
    failed / succeeded / progress. P4 这一轮大多由 worker 写; 现在
    这一张表先建好 schema, 后续 worker 集成时 wire up.
    """

    __tablename__ = "agent_run_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    agent_run_id: Mapped[int] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="CASCADE"), index=True,
    )
    event_type: Mapped[str] = mapped_column(String(40), index=True)
    message: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=None)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow, index=True)
