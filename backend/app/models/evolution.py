"""Evolution models: SkillCard, EvolutionRun, EvolutionPatch, ModelQualityStat."""
from datetime import datetime, timezone
from sqlalchemy import Integer, String, Float, DateTime, Text, JSON, Index
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class SkillCard(Base):
    __tablename__ = "skill_cards"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[int | None] = mapped_column(Integer, nullable=True, default=None)
    source_material_id: Mapped[int | None] = mapped_column(Integer, nullable=True, default=None)
    source_type: Mapped[str] = mapped_column(String(50), default="manual")
    skill_type: Mapped[str] = mapped_column(String(80), nullable=False)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    applicable_genres: Mapped[list | None] = mapped_column(JSON, nullable=True, default=None)
    character_tags: Mapped[list | None] = mapped_column(JSON, nullable=True, default=None)
    situation_tags: Mapped[list | None] = mapped_column(JSON, nullable=True, default=None)
    technique_tags: Mapped[list | None] = mapped_column(JSON, nullable=True, default=None)
    trigger_conditions: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=None)
    prompt_hint: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    anti_pattern: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    checklist: Mapped[list | None] = mapped_column(JSON, nullable=True, default=None)
    evidence_refs: Mapped[list | None] = mapped_column(JSON, nullable=True, default=None)
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    success_score: Mapped[float] = mapped_column(Float, default=0.5)
    usage_count: Mapped[int] = mapped_column(Integer, default=0)
    positive_feedback_count: Mapped[int] = mapped_column(Integer, default=0)
    negative_feedback_count: Mapped[int] = mapped_column(Integer, default=0)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, default=None)
    status: Mapped[str] = mapped_column(String(30), default="candidate")
    parent_skill_id: Mapped[int | None] = mapped_column(Integer, nullable=True, default=None)
    generation: Mapped[int] = mapped_column(Integer, default=1)
    version: Mapped[int] = mapped_column(Integer, default=1)
    content_fingerprint: Mapped[str | None] = mapped_column(String(100), nullable=True, default=None)
    created_by: Mapped[str | None] = mapped_column(String(80), nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.utcnow())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.utcnow(), onupdate=lambda: datetime.utcnow())
    __table_args__ = (Index("ix_skill_status", "status"),)


class SkillVersion(Base):
    __tablename__ = "skill_versions"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    skill_id: Mapped[int] = mapped_column(Integer, nullable=False)
    version_no: Mapped[int] = mapped_column(Integer, default=1)
    prompt_hint: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    anti_pattern: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    checklist: Mapped[list | None] = mapped_column(JSON, nullable=True, default=None)
    change_reason: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    metrics_before: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=None)
    metrics_after: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=None)
    created_by: Mapped[str | None] = mapped_column(String(80), nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.utcnow())


class SkillUsageEvent(Base):
    __tablename__ = "skill_usage_events"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    skill_id: Mapped[int] = mapped_column(Integer, nullable=False)
    project_id: Mapped[int | None] = mapped_column(Integer, nullable=True, default=None)
    chapter_id: Mapped[int | None] = mapped_column(Integer, nullable=True, default=None)
    task_id: Mapped[int | None] = mapped_column(Integer, nullable=True, default=None)
    agent_role: Mapped[str | None] = mapped_column(String(80), nullable=True, default=None)
    injected_into: Mapped[str | None] = mapped_column(String(50), nullable=True, default=None)
    matched_tags: Mapped[list | None] = mapped_column(JSON, nullable=True, default=None)
    prompt_excerpt: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    used_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.utcnow())
    critic_score_before: Mapped[float | None] = mapped_column(Float, nullable=True, default=None)
    critic_score_after: Mapped[float | None] = mapped_column(Float, nullable=True, default=None)
    reader_score: Mapped[float | None] = mapped_column(Float, nullable=True, default=None)
    rewrite_rounds: Mapped[int | None] = mapped_column(Integer, nullable=True, default=None)
    outcome: Mapped[str | None] = mapped_column(String(30), nullable=True, default=None)


class EvolutionRun(Base):
    __tablename__ = "evolution_runs"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[int | None] = mapped_column(Integer, nullable=True, default=None)
    run_type: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="queued")
    trigger_source: Mapped[str | None] = mapped_column(String(50), nullable=True, default=None)
    input_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=None)
    output_summary: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=None)
    proposed_patches: Mapped[list | None] = mapped_column(JSON, nullable=True, default=None)
    applied_patches: Mapped[list | None] = mapped_column(JSON, nullable=True, default=None)
    cost_usd: Mapped[float] = mapped_column(Float, default=0)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, default=None)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.utcnow())


class EvolutionPatch(Base):
    __tablename__ = "evolution_patches"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    evolution_run_id: Mapped[int | None] = mapped_column(Integer, nullable=True, default=None)
    project_id: Mapped[int | None] = mapped_column(Integer, nullable=True, default=None)
    patch_type: Mapped[str] = mapped_column(String(50), nullable=False)
    target_type: Mapped[str | None] = mapped_column(String(50), nullable=True, default=None)
    target_id: Mapped[int | None] = mapped_column(Integer, nullable=True, default=None)
    title: Mapped[str | None] = mapped_column(String(240), nullable=True, default=None)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    before_json: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=None)
    after_json: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=None)
    risk_level: Mapped[str] = mapped_column(String(20), default="low")
    status: Mapped[str] = mapped_column(String(30), default="proposed")
    evaluation_result: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=None)
    created_by_agent_role: Mapped[str | None] = mapped_column(String(80), nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.utcnow())
    applied_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, default=None)


class ModelQualityStat(Base):
    __tablename__ = "model_quality_stats"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    provider_id: Mapped[int | None] = mapped_column(Integer, nullable=True, default=None)
    model_name: Mapped[str] = mapped_column(String(200), nullable=False)
    agent_role_key: Mapped[str | None] = mapped_column(String(80), nullable=True, default=None)
    total_calls: Mapped[int] = mapped_column(Integer, default=0)
    avg_critic_score: Mapped[float | None] = mapped_column(Float, nullable=True, default=None)
    avg_reader_score: Mapped[float | None] = mapped_column(Float, nullable=True, default=None)
    avg_rewrite_rounds: Mapped[float | None] = mapped_column(Float, nullable=True, default=None)
    json_parse_failure_rate: Mapped[float] = mapped_column(Float, default=0)
    hallucination_count: Mapped[int] = mapped_column(Integer, default=0)
    continuity_issue_count: Mapped[int] = mapped_column(Integer, default=0)
    avg_latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True, default=None)
    avg_cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True, default=None)
    window: Mapped[str | None] = mapped_column(String(20), nullable=True, default=None)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.utcnow(), onupdate=lambda: datetime.utcnow())
