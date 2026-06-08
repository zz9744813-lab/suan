"""baseline: 阶段 3.2 引入, 把现有 SQLite 时代的 schema 一次性铺到 PostgreSQL.

包含:
  * projects / chapters / outlines / bibles / chapter_versions
  * agent_tasks / agent_steps / agent_events / worker_status / worker_policies
  * study_materials / study_chapters / study_characters / study_relationships /
    study_foreshadows / study_chapter_summaries / study_scenes / study_techniques /
    study_runs / study_materials_extra
  * memory / memory_v2 / memory_characters / memory_facts / memory_foreshadows /
    evolution_nodes
  * model_providers / model_health / model_call_events / llm_cache_entries /
    model_health_snapshots / model_route_events
  * agent_roles / agent_role_runs / agent_role_messages
  * discussion_* / comment_review_* / chief_agent_*
  * behavior_cards / behavior_card_uses
  * prompt_templates / prompt_versions / template_usages /
    genre_prompt_mappings / prompt_auto_fill_*
  * project_study_material_links / project_study_link_bindings
  * deepstudy_graphs / deepstudy_graph_nodes / deepstudy_graph_edges /
    deepstudy_stage_results
  * audit_logs

补列 (来自 core/database.py 的 _COLUMN_BACKFILLS):
  * projects 增 category / sort_order / pinned / last_opened_at
  * model_providers 增 health 探测字段 + 熔断器字段
  * memory_foreshadows 增 source_material_id
  * study_materials 增 study_status / deepstudy_version / shelf_category /
    cover_theme / study_progress / knowledge_score / last_deepstudied_at
  * prompt_templates 增 immutable
  * agent_model_bindings 增 selection_mode / auto_strategy / candidate_* /
    allow_auto_fallback / failure_threshold / cooldown_seconds / locked_reason /
    last_selected_* / binding_mode / locked_provider_id / locked_model_name /
    lock_reason / locked_by_user / allow_fallback / allow_auto_switch /
    updated_by
  * genre_prompt_mappings 增 source / confidence_score / auto_bind_reason /
    locked_by_user / auto_fill_batch_id / last_effect_score / last_used_at
  * agent_tasks 增 not_before_at / retry_count / max_retries /
    last_failure_type / last_fallback_summary / parent_task_id / visibility /
    domain / task_kind / material_id / run_id / stage_key /
    progress_current / progress_total / display_title / summary_json /
    lease_owner / lease_expires_at / last_heartbeat_at / correlation_id
  * agent_steps 增 is_mock
  * graph_edges 增 count
  * behavior_cards 增 source_pattern_id
  * model_call_events 增 event_type / event_category / level / chapter_id /
    step_key / provider_name / fallback_* / summary / detail_json / cache_hit /
    request_id / error_code

本迁移对 PostgreSQL 使用 JSONB, 对 SQLite 退化为 JSON.
down_revision = None, 视为项目初始版本.
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "20260608_0001_baseline"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# 选用合适 JSON 类型: PG -> JSONB, 其它 -> JSON.
def _json_type() -> sa.types.TypeEngine:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        from sqlalchemy.dialects.postgresql import JSONB

        return JSONB(astext_type=sa.Text())
    return sa.JSON()


def _uuid_default_sql() -> str:
    """PG 用 gen_random_uuid(), SQLite 用随机 hex."""
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        return "gen_random_uuid()"
    # SQLite 没有内置 UUID, 业务层用 uuid4 hex 字符串. 此处留 None.
    return ""


def upgrade() -> None:
    json_t = _json_type()
    bind = op.get_bind()
    is_pg = bind.dialect.name == "postgresql"

    # 在 PG 上启用 pgcrypto (gen_random_uuid).
    if is_pg:
        op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto;")

    # ============================================================
    # 1) projects / chapters / outlines / bibles / chapter_versions
    # ============================================================
    op.create_table(
        "projects",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text, default=""),
        sa.Column("genre", sa.String(60), default=""),
        sa.Column("target_chapter_count", sa.Integer, default=0),
        sa.Column("target_word_count", sa.Integer, default=0),
        sa.Column("status", sa.String(20), default="active", index=True),
        sa.Column("system_flag", sa.String(40), default="", index=True),
        sa.Column("cover_color", sa.String(20), default=""),
        sa.Column("extra", json_t, default=dict),
        sa.Column("created_at", sa.DateTime, default=sa.func.utcnow(), nullable=False),
        sa.Column("updated_at", sa.DateTime, default=sa.func.utcnow(), onupdate=sa.func.utcnow(), nullable=False),
    )
    op.execute("ALTER TABLE projects ADD COLUMN IF NOT EXISTS category VARCHAR(80);")
    op.execute("ALTER TABLE projects ADD COLUMN IF NOT EXISTS sort_order INTEGER DEFAULT 0;")
    op.execute("ALTER TABLE projects ADD COLUMN IF NOT EXISTS pinned BOOLEAN DEFAULT FALSE;")
    op.execute("ALTER TABLE projects ADD COLUMN IF NOT EXISTS last_opened_at TIMESTAMP;")

    op.create_table(
        "bibles",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("project_id", sa.Integer, sa.ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=False),
        sa.Column("version", sa.Integer, default=1),
        sa.Column("is_active", sa.Boolean, default=True, index=True),
        sa.Column("content", json_t, default=dict),
        sa.Column("created_at", sa.DateTime, default=sa.func.utcnow()),
        sa.Column("updated_at", sa.DateTime, default=sa.func.utcnow(), onupdate=sa.func.utcnow()),
    )

    op.create_table(
        "outlines",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("project_id", sa.Integer, sa.ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=False),
        sa.Column("chapter_no", sa.Integer, index=True, nullable=False),
        sa.Column("title", sa.String(240), default=""),
        sa.Column("summary", sa.Text, default=""),
        sa.Column("importance", sa.Integer, default=50),
        sa.Column("target_word_count", sa.Integer, default=3000),
        sa.Column("extra", json_t, default=dict),
        sa.Column("created_at", sa.DateTime, default=sa.func.utcnow()),
        sa.Column("updated_at", sa.DateTime, default=sa.func.utcnow(), onupdate=sa.func.utcnow()),
    )

    op.create_table(
        "chapters",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("project_id", sa.Integer, sa.ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=False),
        sa.Column("outline_id", sa.Integer, sa.ForeignKey("outlines.id", ondelete="SET NULL"), index=True),
        sa.Column("chapter_no", sa.Integer, index=True, nullable=False),
        sa.Column("title", sa.String(240), default=""),
        sa.Column("target_word_count", sa.Integer, default=3000),
        sa.Column("status", sa.String(20), default="queued", index=True),
        sa.Column("locked_by", sa.String(80), default=""),
        sa.Column("last_edited_at", sa.DateTime),
        sa.Column("last_score", sa.Integer),
        sa.Column("rewrite_round", sa.Integer, default=0),
        sa.Column("extra", json_t, default=dict),
        sa.Column("created_at", sa.DateTime, default=sa.func.utcnow()),
        sa.Column("updated_at", sa.DateTime, default=sa.func.utcnow(), onupdate=sa.func.utcnow()),
    )

    op.create_table(
        "chapter_versions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("chapter_id", sa.Integer, sa.ForeignKey("chapters.id", ondelete="CASCADE"), index=True, nullable=False),
        sa.Column("version_kind", sa.String(20), index=True, default="draft"),
        sa.Column("version_no", sa.Integer, default=1),
        sa.Column("content", sa.Text, default=""),
        sa.Column("score", sa.Integer, default=0),
        sa.Column("notes", json_t, default=dict),
        sa.Column("created_at", sa.DateTime, default=sa.func.utcnow()),
        sa.Column("updated_at", sa.DateTime, default=sa.func.utcnow(), onupdate=sa.func.utcnow()),
    )

    # ============================================================
    # 2) tasks: agent_tasks / agent_steps / agent_events /
    #    worker_status / worker_policies
    # ============================================================
    op.create_table(
        "agent_tasks",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("project_id", sa.Integer, sa.ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=False),
        sa.Column("chapter_id", sa.Integer, sa.ForeignKey("chapters.id", ondelete="SET NULL"), index=True),
        sa.Column("task_type", sa.String(50), index=True, nullable=False),
        sa.Column("status", sa.String(20), default="pending", index=True),
        sa.Column("priority", sa.Integer, default=100),
        sa.Column("payload", json_t, default=dict),
        sa.Column("error", sa.Text),
        sa.Column("retry_count", sa.Integer, default=0),
        sa.Column("max_retries", sa.Integer, default=3),
        sa.Column("cost_usd", sa.Float, default=0.0),
        sa.Column("input_tokens", sa.Integer, default=0),
        sa.Column("output_tokens", sa.Integer, default=0),
        sa.Column("started_at", sa.DateTime),
        sa.Column("finished_at", sa.DateTime),
        sa.Column("not_before_at", sa.DateTime, index=True),
        sa.Column("lease_owner", sa.String(120), index=True),
        sa.Column("lease_expires_at", sa.DateTime, index=True),
        sa.Column("last_heartbeat_at", sa.DateTime, index=True),
        sa.Column("correlation_id", sa.String(120), index=True),
        sa.Column("parent_task_id", sa.Integer),
        sa.Column("visibility", sa.String(30), default="user"),
        sa.Column("domain", sa.String(50), default="writing"),
        sa.Column("task_kind", sa.String(80)),
        sa.Column("material_id", sa.Integer),
        sa.Column("run_id", sa.Integer),
        sa.Column("stage_key", sa.String(80)),
        sa.Column("progress_current", sa.Integer, default=0),
        sa.Column("progress_total", sa.Integer, default=0),
        sa.Column("display_title", sa.String(240)),
        sa.Column("summary_json", json_t),
        sa.Column("last_failure_type", sa.String(80)),
        sa.Column("last_fallback_summary", json_t),
        sa.Column("created_at", sa.DateTime, default=sa.func.utcnow()),
        sa.Column("updated_at", sa.DateTime, default=sa.func.utcnow(), onupdate=sa.func.utcnow()),
    )

    op.create_table(
        "agent_steps",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("task_id", sa.Integer, sa.ForeignKey("agent_tasks.id", ondelete="CASCADE"), index=True, nullable=False),
        sa.Column("project_id", sa.Integer, sa.ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=False),
        sa.Column("chapter_id", sa.Integer, sa.ForeignKey("chapters.id", ondelete="SET NULL"), index=True),
        sa.Column("agent_name", sa.String(50), index=True, nullable=False),
        sa.Column("step_name", sa.String(80), nullable=False),
        sa.Column("status", sa.String(20), default="pending"),
        sa.Column("input_prompt", sa.Text),
        sa.Column("raw_output", sa.Text),
        sa.Column("parsed_output", json_t),
        sa.Column("model_name", sa.String(120)),
        sa.Column("provider_name", sa.String(120)),
        sa.Column("prompt_template_id", sa.Integer),
        sa.Column("prompt_version", sa.Integer),
        sa.Column("input_tokens", sa.Integer, default=0),
        sa.Column("output_tokens", sa.Integer, default=0),
        sa.Column("cost_usd", sa.Float, default=0.0),
        sa.Column("duration_ms", sa.Integer, default=0),
        sa.Column("error_message", sa.Text),
        sa.Column("started_at", sa.DateTime),
        sa.Column("finished_at", sa.DateTime),
        sa.Column("is_mock", sa.Boolean, default=False),
        sa.Column("created_at", sa.DateTime, default=sa.func.utcnow()),
    )

    op.create_table(
        "agent_events",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("project_id", sa.Integer, sa.ForeignKey("projects.id", ondelete="SET NULL"), index=True),
        sa.Column("chapter_id", sa.Integer, sa.ForeignKey("chapters.id", ondelete="SET NULL"), index=True),
        sa.Column("task_id", sa.Integer, sa.ForeignKey("agent_tasks.id", ondelete="SET NULL"), index=True),
        sa.Column("event_type", sa.String(60), index=True),
        sa.Column("level", sa.String(10), default="info"),
        sa.Column("message", sa.Text, default=""),
        sa.Column("data", json_t),
        sa.Column("created_at", sa.DateTime, default=sa.func.utcnow(), index=True),
    )

    op.create_table(
        "worker_status",
        sa.Column("id", sa.Integer, primary_key=True, default=1),
        sa.Column("state", sa.String(20), default="idle"),
        sa.Column("current_task_id", sa.Integer),
        sa.Column("last_heartbeat_at", sa.DateTime),
        sa.Column("consecutive_failures", sa.Integer, default=0),
        sa.Column("today_words", sa.Integer, default=0),
        sa.Column("today_cost_usd", sa.Float, default=0.0),
        sa.Column("last_reset_date", sa.String(10)),
        sa.Column("last_error", sa.Text),
        sa.Column("updated_at", sa.DateTime, default=sa.func.utcnow(), onupdate=sa.func.utcnow()),
    )

    op.create_table(
        "worker_policies",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("project_id", sa.Integer, sa.ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=False),
        sa.Column("daily_word_goal", sa.Integer, default=30000),
        sa.Column("daily_budget_usd", sa.Float, default=8.0),
        sa.Column("pass_score", sa.Integer, default=80),
        sa.Column("max_rewrite_rounds", sa.Integer, default=2),
        sa.Column("max_retry_per_task", sa.Integer, default=3),
        sa.Column("consecutive_fail_stop", sa.Integer, default=3),
        sa.Column("auto_continue", sa.Boolean, default=True),
        sa.Column("discussion_policy", sa.String(20), default="smart"),
        sa.Column("max_discussion_per_day", sa.Integer, default=5),
        sa.Column("max_cost_per_discussion", sa.Float, default=0.2),
        sa.Column("created_at", sa.DateTime, default=sa.func.utcnow()),
        sa.Column("updated_at", sa.DateTime, default=sa.func.utcnow(), onupdate=sa.func.utcnow()),
    )

    # ============================================================
    # 3) study_* (拆书) — 简化为基线表 + 列补强
    # ============================================================
    op.create_table(
        "study_materials",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("project_id", sa.Integer, sa.ForeignKey("projects.id", ondelete="SET NULL"), index=True),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("author", sa.String(160), default=""),
        sa.Column("source", sa.String(40), default="paste"),
        sa.Column("raw_text", sa.Text, default=""),
        sa.Column("status", sa.String(20), default="draft"),
        sa.Column("error", sa.Text),
        sa.Column("chapter_count", sa.Integer, default=0),
        sa.Column("character_count", sa.Integer, default=0),
        sa.Column("extra", json_t, default=dict),
        sa.Column("created_at", sa.DateTime, default=sa.func.utcnow()),
        sa.Column("updated_at", sa.DateTime, default=sa.func.utcnow(), onupdate=sa.func.utcnow()),
    )
    for ddl in (
        "ALTER TABLE study_materials ADD COLUMN IF NOT EXISTS study_status VARCHAR(40) DEFAULT 'empty'",
        "ALTER TABLE study_materials ADD COLUMN IF NOT EXISTS deepstudy_version VARCHAR(40)",
        "ALTER TABLE study_materials ADD COLUMN IF NOT EXISTS shelf_category VARCHAR(80)",
        "ALTER TABLE study_materials ADD COLUMN IF NOT EXISTS cover_theme JSON",
        "ALTER TABLE study_materials ADD COLUMN IF NOT EXISTS study_progress JSON",
        "ALTER TABLE study_materials ADD COLUMN IF NOT EXISTS knowledge_score FLOAT",
        "ALTER TABLE study_materials ADD COLUMN IF NOT EXISTS last_deepstudied_at TIMESTAMP",
    ):
        op.execute(ddl)

    op.create_table(
        "study_chapters",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("material_id", sa.Integer, sa.ForeignKey("study_materials.id", ondelete="CASCADE"), index=True, nullable=False),
        sa.Column("chapter_index", sa.Integer, index=True, nullable=False),
        sa.Column("title", sa.String(240), default=""),
        sa.Column("content", sa.Text, default=""),
        sa.Column("char_count", sa.Integer, default=0),
        sa.Column("extra", json_t, default=dict),
        sa.Column("created_at", sa.DateTime, default=sa.func.utcnow()),
        sa.Column("updated_at", sa.DateTime, default=sa.func.utcnow(), onupdate=sa.func.utcnow()),
    )

    op.create_table(
        "study_characters",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("material_id", sa.Integer, sa.ForeignKey("study_materials.id", ondelete="CASCADE"), index=True, nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("aliases", json_t, default=list),
        sa.Column("role", sa.String(40), default="supporting"),
        sa.Column("summary", sa.Text, default=""),
        sa.Column("profile", json_t, default=dict),
        sa.Column("first_chapter", sa.Integer),
        sa.Column("last_chapter", sa.Integer),
        sa.Column("extra", json_t, default=dict),
        sa.Column("created_at", sa.DateTime, default=sa.func.utcnow()),
        sa.Column("updated_at", sa.DateTime, default=sa.func.utcnow(), onupdate=sa.func.utcnow()),
    )

    op.create_table(
        "study_relationships",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("material_id", sa.Integer, sa.ForeignKey("study_materials.id", ondelete="CASCADE"), index=True, nullable=False),
        sa.Column("source_id", sa.Integer, sa.ForeignKey("study_characters.id", ondelete="CASCADE"), index=True),
        sa.Column("target_id", sa.Integer, sa.ForeignKey("study_characters.id", ondelete="CASCADE"), index=True),
        sa.Column("relation", sa.String(80), default=""),
        sa.Column("summary", sa.Text, default=""),
        sa.Column("extra", json_t, default=dict),
        sa.Column("created_at", sa.DateTime, default=sa.func.utcnow()),
        sa.Column("updated_at", sa.DateTime, default=sa.func.utcnow(), onupdate=sa.func.utcnow()),
    )

    op.create_table(
        "study_foreshadows",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("material_id", sa.Integer, sa.ForeignKey("study_materials.id", ondelete="CASCADE"), index=True, nullable=False),
        sa.Column("title", sa.String(240), default=""),
        sa.Column("summary", sa.Text, default=""),
        sa.Column("status", sa.String(20), default="open"),
        sa.Column("source_chapter", sa.Integer),
        sa.Column("reveal_chapter", sa.Integer),
        sa.Column("extra", json_t, default=dict),
        sa.Column("created_at", sa.DateTime, default=sa.func.utcnow()),
        sa.Column("updated_at", sa.DateTime, default=sa.func.utcnow(), onupdate=sa.func.utcnow()),
    )

    op.create_table(
        "study_chapter_summaries",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("material_id", sa.Integer, sa.ForeignKey("study_materials.id", ondelete="CASCADE"), index=True, nullable=False),
        sa.Column("chapter_id", sa.Integer, sa.ForeignKey("study_chapters.id", ondelete="CASCADE"), index=True),
        sa.Column("summary", sa.Text, default=""),
        sa.Column("key_points", json_t, default=list),
        sa.Column("extra", json_t, default=dict),
        sa.Column("created_at", sa.DateTime, default=sa.func.utcnow()),
    )

    op.create_table(
        "study_scenes",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("material_id", sa.Integer, sa.ForeignKey("study_materials.id", ondelete="CASCADE"), index=True, nullable=False),
        sa.Column("chapter_id", sa.Integer, sa.ForeignKey("study_chapters.id", ondelete="CASCADE"), index=True),
        sa.Column("scene_index", sa.Integer, default=0),
        sa.Column("title", sa.String(240), default=""),
        sa.Column("summary", sa.Text, default=""),
        sa.Column("emotion", sa.String(40), default=""),
        sa.Column("extra", json_t, default=dict),
        sa.Column("created_at", sa.DateTime, default=sa.func.utcnow()),
    )

    op.create_table(
        "study_techniques",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("material_id", sa.Integer, sa.ForeignKey("study_materials.id", ondelete="CASCADE"), index=True, nullable=False),
        sa.Column("category", sa.String(60), default=""),
        sa.Column("title", sa.String(240), default=""),
        sa.Column("description", sa.Text, default=""),
        sa.Column("evidence_chapter", sa.Integer),
        sa.Column("extra", json_t, default=dict),
        sa.Column("created_at", sa.DateTime, default=sa.func.utcnow()),
    )

    op.create_table(
        "study_runs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("material_id", sa.Integer, sa.ForeignKey("study_materials.id", ondelete="CASCADE"), index=True, nullable=False),
        sa.Column("project_id", sa.Integer, sa.ForeignKey("projects.id", ondelete="SET NULL"), index=True),
        sa.Column("status", sa.String(20), default="queued", index=True),
        sa.Column("mode", sa.String(20), default="full"),
        sa.Column("total_chapters", sa.Integer, default=0),
        sa.Column("processed_chapters", sa.Integer, default=0),
        sa.Column("current_stage", sa.String(80)),
        sa.Column("agent_plan", json_t, default=dict),
        sa.Column("progress", json_t, default=dict),
        sa.Column("error", sa.Text),
        sa.Column("started_at", sa.DateTime),
        sa.Column("finished_at", sa.DateTime),
        sa.Column("created_at", sa.DateTime, default=sa.func.utcnow()),
        sa.Column("updated_at", sa.DateTime, default=sa.func.utcnow(), onupdate=sa.func.utcnow()),
    )

    op.create_table(
        "project_study_material_links",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("project_id", sa.Integer, sa.ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=False),
        sa.Column("material_id", sa.Integer, sa.ForeignKey("study_materials.id", ondelete="CASCADE"), index=True, nullable=False),
        sa.Column("link_type", sa.String(50), default="reference"),
        sa.Column("weight", sa.Float, default=1.0),
        sa.Column("enabled", sa.Boolean, default=True),
        sa.Column("created_at", sa.DateTime, default=sa.func.utcnow()),
        sa.Column("updated_at", sa.DateTime, default=sa.func.utcnow(), onupdate=sa.func.utcnow()),
        sa.UniqueConstraint("project_id", "material_id", name="uq_project_study_material"),
    )

    # ============================================================
    # 4) deepstudy_graphs / nodes / edges / stage_results
    # ============================================================
    op.create_table(
        "deepstudy_graphs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("material_id", sa.Integer, sa.ForeignKey("study_materials.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("status", sa.String(40), default="not_started"),
        sa.Column("graph_version", sa.Integer, default=1),
        sa.Column("node_count", sa.Integer, default=0),
        sa.Column("edge_count", sa.Integer, default=0),
        sa.Column("character_count", sa.Integer, default=0),
        sa.Column("location_count", sa.Integer, default=0),
        sa.Column("faction_count", sa.Integer, default=0),
        sa.Column("item_count", sa.Integer, default=0),
        sa.Column("event_count", sa.Integer, default=0),
        sa.Column("foreshadow_count", sa.Integer, default=0),
        sa.Column("behavior_pattern_count", sa.Integer, default=0),
        sa.Column("writing_technique_count", sa.Integer, default=0),
        sa.Column("layout_json", sa.Text),
        sa.Column("stats_json", sa.Text),
        sa.Column("last_error", sa.Text),
        sa.Column("built_at", sa.DateTime),
        sa.Column("created_at", sa.DateTime, default=sa.func.utcnow()),
        sa.Column("updated_at", sa.DateTime, default=sa.func.utcnow(), onupdate=sa.func.utcnow()),
    )

    op.create_table(
        "deepstudy_graph_nodes",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("material_id", sa.Integer, sa.ForeignKey("study_materials.id", ondelete="CASCADE"), index=True, nullable=False),
        sa.Column("node_key", sa.String(240), nullable=False),
        sa.Column("node_type", sa.String(80), nullable=False),
        sa.Column("label", sa.String(240), nullable=False),
        sa.Column("summary", sa.Text),
        sa.Column("importance", sa.Float, default=0.5),
        sa.Column("confidence", sa.Float, default=0.5),
        sa.Column("first_seen_chapter", sa.Integer),
        sa.Column("last_seen_chapter", sa.Integer),
        sa.Column("source_stage", sa.String(80)),
        sa.Column("payload_json", sa.Text),
        sa.Column("evidence_json", sa.Text),
        sa.Column("x", sa.Float),
        sa.Column("y", sa.Float),
        sa.Column("created_at", sa.DateTime, default=sa.func.utcnow()),
        sa.Column("updated_at", sa.DateTime, default=sa.func.utcnow(), onupdate=sa.func.utcnow()),
        sa.UniqueConstraint("material_id", "node_key", name="uq_deepstudy_node_key"),
    )

    op.create_table(
        "deepstudy_graph_edges",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("material_id", sa.Integer, sa.ForeignKey("study_materials.id", ondelete="CASCADE"), index=True, nullable=False),
        sa.Column("edge_key", sa.String(320), nullable=False),
        sa.Column("source_node_key", sa.String(240), nullable=False),
        sa.Column("target_node_key", sa.String(240), nullable=False),
        sa.Column("source_node_id", sa.Integer),
        sa.Column("target_node_id", sa.Integer),
        sa.Column("edge_type", sa.String(80), nullable=False),
        sa.Column("label", sa.String(160), nullable=False),
        sa.Column("summary", sa.Text),
        sa.Column("direction", sa.String(30), default="directed"),
        sa.Column("weight", sa.Float, default=0.5),
        sa.Column("confidence", sa.Float, default=0.5),
        sa.Column("source_stage", sa.String(80)),
        sa.Column("evidence_json", sa.Text),
        sa.Column("payload_json", sa.Text),
        sa.Column("first_seen_chapter", sa.Integer),
        sa.Column("last_seen_chapter", sa.Integer),
        sa.Column("occurrence_count", sa.Integer, default=1),
        sa.Column("created_at", sa.DateTime, default=sa.func.utcnow()),
        sa.Column("updated_at", sa.DateTime, default=sa.func.utcnow(), onupdate=sa.func.utcnow()),
        sa.UniqueConstraint("material_id", "edge_key", name="uq_deepstudy_edge_key"),
    )

    op.create_table(
        "deepstudy_stage_results",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("run_id", sa.Integer, sa.ForeignKey("study_runs.id", ondelete="CASCADE"), index=True, nullable=False),
        sa.Column("material_id", sa.Integer, sa.ForeignKey("study_materials.id", ondelete="CASCADE"), index=True, nullable=False),
        sa.Column("chapter_id", sa.Integer, sa.ForeignKey("study_chapters.id", ondelete="SET NULL"), index=True),
        sa.Column("chapter_index", sa.Integer),
        sa.Column("stage_key", sa.String(80), nullable=False),
        sa.Column("status", sa.String(30), default="pending"),
        sa.Column("input_snapshot", sa.Text),
        sa.Column("output_json", sa.Text),
        sa.Column("raw_output", sa.Text),
        sa.Column("error_message", sa.Text),
        sa.Column("provider_name", sa.String(120)),
        sa.Column("model_name", sa.String(200)),
        sa.Column("input_tokens", sa.Integer, default=0),
        sa.Column("output_tokens", sa.Integer, default=0),
        sa.Column("cost_usd", sa.Float, default=0.0),
        sa.Column("duration_ms", sa.Integer, default=0),
        sa.Column("retry_count", sa.Integer, default=0),
        sa.Column("created_at", sa.DateTime, default=sa.func.utcnow()),
        sa.Column("updated_at", sa.DateTime, default=sa.func.utcnow(), onupdate=sa.func.utcnow()),
    )

    # ============================================================
    # 5) memory* / evolution*
    # ============================================================
    op.create_table(
        "memory_characters",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("project_id", sa.Integer, sa.ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("role", sa.String(40), default="supporting"),
        sa.Column("profile", json_t, default=dict),
        sa.Column("state", json_t, default=dict),
        sa.Column("extra", json_t, default=dict),
        sa.Column("created_at", sa.DateTime, default=sa.func.utcnow()),
        sa.Column("updated_at", sa.DateTime, default=sa.func.utcnow(), onupdate=sa.func.utcnow()),
    )

    op.create_table(
        "memory_facts",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("project_id", sa.Integer, sa.ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=False),
        sa.Column("chapter_id", sa.Integer, sa.ForeignKey("chapters.id", ondelete="SET NULL"), index=True),
        sa.Column("category", sa.String(40), default="world"),
        sa.Column("subject", sa.String(160), default=""),
        sa.Column("predicate", sa.String(80), default=""),
        sa.Column("object", sa.Text, default=""),
        sa.Column("confidence", sa.Float, default=0.5),
        sa.Column("extra", json_t, default=dict),
        sa.Column("created_at", sa.DateTime, default=sa.func.utcnow()),
    )

    op.create_table(
        "memory_foreshadows",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("project_id", sa.Integer, sa.ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=False),
        sa.Column("title", sa.String(240), default=""),
        sa.Column("summary", sa.Text, default=""),
        sa.Column("status", sa.String(20), default="open"),
        sa.Column("source_chapter", sa.Integer),
        sa.Column("reveal_chapter", sa.Integer),
        sa.Column("source_material_id", sa.Integer, index=True),
        sa.Column("extra", json_t, default=dict),
        sa.Column("created_at", sa.DateTime, default=sa.func.utcnow()),
        sa.Column("updated_at", sa.DateTime, default=sa.func.utcnow(), onupdate=sa.func.utcnow()),
    )

    op.create_table(
        "evolution_nodes",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("material_id", sa.Integer, index=True),
        sa.Column("run_id", sa.Integer, index=True),
        sa.Column("chapter_id", sa.Integer, index=True),
        sa.Column("kind", sa.String(60), default=""),
        sa.Column("payload", json_t, default=dict),
        sa.Column("created_at", sa.DateTime, default=sa.func.utcnow()),
    )

    # ============================================================
    # 6) model_providers / model_health* / model_call_events
    # ============================================================
    op.create_table(
        "model_providers",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(120), unique=True, nullable=False),
        sa.Column("base_url", sa.String(400), default=""),
        sa.Column("api_key", sa.String(400), default=""),
        sa.Column("kind", sa.String(40), default="openai"),
        sa.Column("enabled", sa.Boolean, default=True),
        sa.Column("extra", json_t, default=dict),
        sa.Column("created_at", sa.DateTime, default=sa.func.utcnow()),
        sa.Column("updated_at", sa.DateTime, default=sa.func.utcnow(), onupdate=sa.func.utcnow()),
    )
    for ddl in (
        "ALTER TABLE model_providers ADD COLUMN IF NOT EXISTS last_health_status VARCHAR(20)",
        "ALTER TABLE model_providers ADD COLUMN IF NOT EXISTS last_health_message TEXT",
        "ALTER TABLE model_providers ADD COLUMN IF NOT EXISTS last_health_latency_ms INTEGER",
        "ALTER TABLE model_providers ADD COLUMN IF NOT EXISTS last_health_model VARCHAR(120)",
        "ALTER TABLE model_providers ADD COLUMN IF NOT EXISTS last_health_at TIMESTAMP",
        "ALTER TABLE model_providers ADD COLUMN IF NOT EXISTS last_health_full JSON",
        "ALTER TABLE model_providers ADD COLUMN IF NOT EXISTS health_score FLOAT DEFAULT 0.75",
        "ALTER TABLE model_providers ADD COLUMN IF NOT EXISTS success_rate_1h FLOAT DEFAULT 1.0",
        "ALTER TABLE model_providers ADD COLUMN IF NOT EXISTS success_rate_24h FLOAT DEFAULT 1.0",
        "ALTER TABLE model_providers ADD COLUMN IF NOT EXISTS avg_latency_ms INTEGER",
        "ALTER TABLE model_providers ADD COLUMN IF NOT EXISTS consecutive_failures INTEGER DEFAULT 0",
        "ALTER TABLE model_providers ADD COLUMN IF NOT EXISTS consecutive_successes INTEGER DEFAULT 0",
        "ALTER TABLE model_providers ADD COLUMN IF NOT EXISTS circuit_state VARCHAR(20) DEFAULT 'closed'",
        "ALTER TABLE model_providers ADD COLUMN IF NOT EXISTS circuit_open_until TIMESTAMP",
        "ALTER TABLE model_providers ADD COLUMN IF NOT EXISTS last_failure_type VARCHAR(60)",
        "ALTER TABLE model_providers ADD COLUMN IF NOT EXISTS last_failure_message TEXT",
        "ALTER TABLE model_providers ADD COLUMN IF NOT EXISTS last_success_at TIMESTAMP",
        "ALTER TABLE model_providers ADD COLUMN IF NOT EXISTS daily_cost_usd FLOAT DEFAULT 0.0",
        "ALTER TABLE model_providers ADD COLUMN IF NOT EXISTS daily_request_count INTEGER DEFAULT 0",
        "ALTER TABLE model_providers ADD COLUMN IF NOT EXISTS daily_token_count INTEGER DEFAULT 0",
        "ALTER TABLE model_providers ADD COLUMN IF NOT EXISTS last_reset_date VARCHAR(10)",
    ):
        op.execute(ddl)

    op.create_table(
        "model_health_snapshots",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("provider_id", sa.Integer, sa.ForeignKey("model_providers.id", ondelete="CASCADE"), index=True, nullable=False),
        sa.Column("model_name", sa.String(200), nullable=False),
        sa.Column("status", sa.String(40), default="unknown"),
        sa.Column("health_score", sa.Float, default=0),
        sa.Column("success_rate", sa.Float, default=0),
        sa.Column("error_rate", sa.Float, default=0),
        sa.Column("avg_latency_ms", sa.Integer, default=0),
        sa.Column("p95_latency_ms", sa.Integer, default=0),
        sa.Column("last_success_at", sa.DateTime),
        sa.Column("last_failure_at", sa.DateTime),
        sa.Column("last_error_code", sa.String(80)),
        sa.Column("last_error_message", sa.Text),
        sa.Column("supports_text", sa.Boolean, default=True),
        sa.Column("supports_image", sa.Boolean, default=False),
        sa.Column("supports_video", sa.Boolean, default=False),
        sa.Column("supports_json", sa.Boolean, default=False),
        sa.Column("supports_stream", sa.Boolean, default=False),
        sa.Column("context_window", sa.Integer),
        sa.Column("max_output_tokens", sa.Integer),
        sa.Column("input_price_per_million", sa.Float),
        sa.Column("output_price_per_million", sa.Float),
        sa.Column("rate_limited_until", sa.DateTime),
        sa.Column("cooldown_until", sa.DateTime),
        sa.Column("probe_count", sa.Integer, default=0),
        sa.Column("consecutive_failures", sa.Integer, default=0),
        sa.Column("created_at", sa.DateTime, default=sa.func.utcnow()),
        sa.Column("updated_at", sa.DateTime, default=sa.func.utcnow(), onupdate=sa.func.utcnow()),
        sa.UniqueConstraint("provider_id", "model_name", name="uq_provider_model"),
    )

    op.create_table(
        "model_route_events",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("task_id", sa.Integer),
        sa.Column("step_id", sa.Integer),
        sa.Column("agent_role_key", sa.String(120), nullable=False),
        sa.Column("binding_mode", sa.String(40), nullable=False),
        sa.Column("strategy", sa.String(80)),
        sa.Column("selected_provider_id", sa.Integer),
        sa.Column("selected_model_name", sa.String(200)),
        sa.Column("attempted_provider_id", sa.Integer),
        sa.Column("attempted_model_name", sa.String(200)),
        sa.Column("route_reason", sa.String(120), nullable=False),
        sa.Column("locked", sa.Boolean, default=False),
        sa.Column("fallback_used", sa.Boolean, default=False),
        sa.Column("fallback_reason", sa.Text),
        sa.Column("health_score", sa.Float),
        sa.Column("latency_ms", sa.Integer),
        sa.Column("error_code", sa.String(80)),
        sa.Column("error_message", sa.Text),
        sa.Column("created_at", sa.DateTime, default=sa.func.utcnow()),
    )

    op.create_table(
        "model_call_events",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("project_id", sa.Integer, sa.ForeignKey("projects.id", ondelete="SET NULL"), index=True),
        sa.Column("provider_id", sa.Integer, sa.ForeignKey("model_providers.id", ondelete="SET NULL"), index=True),
        sa.Column("model_name", sa.String(200), default=""),
        sa.Column("event_type", sa.String(50), index=True),
        sa.Column("event_category", sa.String(50)),
        sa.Column("level", sa.String(20)),
        sa.Column("task_id", sa.Integer, index=True),
        sa.Column("chapter_id", sa.Integer, sa.ForeignKey("chapters.id", ondelete="SET NULL")),
        sa.Column("step_key", sa.String(50)),
        sa.Column("provider_name", sa.String(120)),
        sa.Column("fallback_from_provider", sa.String(120)),
        sa.Column("fallback_from_model", sa.String(200)),
        sa.Column("fallback_to_provider", sa.String(120)),
        sa.Column("fallback_to_model", sa.String(200)),
        sa.Column("input_tokens", sa.Integer, default=0),
        sa.Column("output_tokens", sa.Integer, default=0),
        sa.Column("cost_usd", sa.Float, default=0.0),
        sa.Column("duration_ms", sa.Integer, default=0),
        sa.Column("summary", sa.Text),
        sa.Column("detail_json", sa.Text),
        sa.Column("cache_hit", sa.Boolean),
        sa.Column("request_id", sa.String(120), index=True),
        sa.Column("error_code", sa.String(80)),
        sa.Column("created_at", sa.DateTime, default=sa.func.utcnow(), index=True),
    )

    op.create_table(
        "llm_cache_entries",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("request_id", sa.String(120), nullable=False, unique=True),
        sa.Column("request_hash", sa.String(80), nullable=False, unique=True),
        sa.Column("provider_id", sa.Integer),
        sa.Column("provider_name", sa.String(120)),
        sa.Column("model_name", sa.String(200)),
        sa.Column("agent_role_key", sa.String(80)),
        sa.Column("step_key", sa.String(80)),
        sa.Column("request_json", json_t),
        sa.Column("response_content", sa.Text, default=""),
        sa.Column("response_raw", json_t),
        sa.Column("response_model", sa.String(200)),
        sa.Column("input_tokens", sa.Integer, default=0),
        sa.Column("output_tokens", sa.Integer, default=0),
        sa.Column("cost_usd", sa.Float, default=0.0),
        sa.Column("duration_ms", sa.Integer, default=0),
        sa.Column("hit_count", sa.Integer, default=0),
        sa.Column("created_at", sa.DateTime, default=sa.func.utcnow()),
        sa.Column("updated_at", sa.DateTime, default=sa.func.utcnow(), onupdate=sa.func.utcnow()),
        sa.Column("last_hit_at", sa.DateTime),
    )

    # ============================================================
    # 7) prompt_templates / prompt_versions / template_usages /
    #    genre_prompt_mappings / prompt_auto_fill_*
    # ============================================================
    op.create_table(
        "prompt_templates",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("key", sa.String(120), unique=True, index=True, nullable=False),
        sa.Column("name", sa.String(240), default=""),
        sa.Column("category", sa.String(60), default=""),
        sa.Column("description", sa.Text, default=""),
        sa.Column("immutable", sa.Boolean, default=False),
        sa.Column("extra", json_t, default=dict),
        sa.Column("created_at", sa.DateTime, default=sa.func.utcnow()),
        sa.Column("updated_at", sa.DateTime, default=sa.func.utcnow(), onupdate=sa.func.utcnow()),
    )

    op.create_table(
        "prompt_versions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("template_id", sa.Integer, sa.ForeignKey("prompt_templates.id", ondelete="CASCADE"), index=True, nullable=False),
        sa.Column("version", sa.Integer, default=1),
        sa.Column("content", sa.Text, default=""),
        sa.Column("variables", json_t, default=list),
        sa.Column("notes", sa.Text, default=""),
        sa.Column("is_active", sa.Boolean, default=True),
        sa.Column("created_at", sa.DateTime, default=sa.func.utcnow()),
    )

    op.create_table(
        "template_usages",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("template_id", sa.Integer, sa.ForeignKey("prompt_templates.id", ondelete="CASCADE"), index=True),
        sa.Column("version_id", sa.Integer, sa.ForeignKey("prompt_versions.id", ondelete="SET NULL")),
        sa.Column("project_id", sa.Integer, sa.ForeignKey("projects.id", ondelete="CASCADE"), index=True),
        sa.Column("chapter_id", sa.Integer, sa.ForeignKey("chapters.id", ondelete="SET NULL"), index=True),
        sa.Column("agent_role_key", sa.String(80)),
        sa.Column("created_at", sa.DateTime, default=sa.func.utcnow()),
    )

    op.create_table(
        "genre_prompt_mappings",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("genre", sa.String(60), index=True),
        sa.Column("template_id", sa.Integer, sa.ForeignKey("prompt_templates.id", ondelete="CASCADE"), index=True),
        sa.Column("source", sa.String(30), default="manual"),
        sa.Column("confidence_score", sa.Float),
        sa.Column("auto_bind_reason", sa.Text),
        sa.Column("locked_by_user", sa.Boolean, default=False),
        sa.Column("auto_fill_batch_id", sa.String(80)),
        sa.Column("last_effect_score", sa.Float),
        sa.Column("last_used_at", sa.DateTime),
        sa.Column("created_at", sa.DateTime, default=sa.func.utcnow()),
        sa.Column("updated_at", sa.DateTime, default=sa.func.utcnow(), onupdate=sa.func.utcnow()),
    )

    op.create_table(
        "prompt_auto_fill_batches",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("batch_id", sa.String(80), unique=True, nullable=False),
        sa.Column("status", sa.String(20), default="running"),
        sa.Column("total", sa.Integer, default=0),
        sa.Column("done", sa.Integer, default=0),
        sa.Column("failed", sa.Integer, default=0),
        sa.Column("summary", json_t, default=dict),
        sa.Column("created_at", sa.DateTime, default=sa.func.utcnow()),
        sa.Column("updated_at", sa.DateTime, default=sa.func.utcnow(), onupdate=sa.func.utcnow()),
    )

    op.create_table(
        "agent_model_bindings",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("agent_role_key", sa.String(80), index=True, nullable=False),
        sa.Column("project_id", sa.Integer, sa.ForeignKey("projects.id", ondelete="CASCADE"), index=True),
        sa.Column("selection_mode", sa.String(30), default="auto"),
        sa.Column("auto_strategy", sa.String(40), default="quality_first"),
        sa.Column("candidate_provider_ids", json_t),
        sa.Column("candidate_models_json", json_t),
        sa.Column("fallback_candidates_json", json_t),
        sa.Column("allow_auto_fallback", sa.Boolean, default=True),
        sa.Column("failure_threshold", sa.Integer, default=2),
        sa.Column("cooldown_seconds", sa.Integer, default=300),
        sa.Column("locked_reason", sa.Text),
        sa.Column("last_selected_provider_id", sa.Integer),
        sa.Column("last_selected_model_name", sa.String(200)),
        sa.Column("last_selection_reason", sa.Text),
        sa.Column("last_selection_score", sa.Float),
        sa.Column("last_selection_at", sa.DateTime),
        sa.Column("binding_mode", sa.String(40), default="auto"),
        sa.Column("locked_provider_id", sa.Integer),
        sa.Column("locked_model_name", sa.String(200)),
        sa.Column("lock_reason", sa.Text),
        sa.Column("locked_by_user", sa.Boolean, default=False),
        sa.Column("allow_fallback", sa.Boolean, default=True),
        sa.Column("allow_auto_switch", sa.Boolean, default=True),
        sa.Column("updated_by", sa.String(120)),
        sa.Column("created_at", sa.DateTime, default=sa.func.utcnow()),
        sa.Column("updated_at", sa.DateTime, default=sa.func.utcnow(), onupdate=sa.func.utcnow()),
    )

    # ============================================================
    # 8) behavior_cards / behavior_card_uses
    # ============================================================
    op.create_table(
        "behavior_cards",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("material_id", sa.Integer, sa.ForeignKey("study_materials.id", ondelete="SET NULL"), index=True),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("category", sa.String(60), default=""),
        sa.Column("description", sa.Text, default=""),
        sa.Column("trigger", sa.Text, default=""),
        sa.Column("outcome", sa.Text, default=""),
        sa.Column("tags", json_t, default=list),
        sa.Column("source_pattern_id", sa.Integer),
        sa.Column("extra", json_t, default=dict),
        sa.Column("created_at", sa.DateTime, default=sa.func.utcnow()),
    )

    op.create_table(
        "behavior_card_uses",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("card_id", sa.Integer, sa.ForeignKey("behavior_cards.id", ondelete="CASCADE"), index=True, nullable=False),
        sa.Column("chapter_id", sa.Integer, sa.ForeignKey("chapters.id", ondelete="SET NULL"), index=True),
        sa.Column("note", sa.Text, default=""),
        sa.Column("created_at", sa.DateTime, default=sa.func.utcnow()),
    )

    # ============================================================
    # 9) discussion / chief_agent / comment_review
    # ============================================================
    op.create_table(
        "discussion_sessions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("project_id", sa.Integer, sa.ForeignKey("projects.id", ondelete="CASCADE"), index=True),
        sa.Column("chapter_id", sa.Integer, sa.ForeignKey("chapters.id", ondelete="SET NULL"), index=True),
        sa.Column("topic", sa.String(240), default=""),
        sa.Column("status", sa.String(20), default="open"),
        sa.Column("round", sa.Integer, default=0),
        sa.Column("extra", json_t, default=dict),
        sa.Column("created_at", sa.DateTime, default=sa.func.utcnow()),
    )

    op.create_table(
        "discussion_messages",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("session_id", sa.Integer, sa.ForeignKey("discussion_sessions.id", ondelete="CASCADE"), index=True, nullable=False),
        sa.Column("role", sa.String(40), default=""),
        sa.Column("speaker_key", sa.String(80), default=""),
        sa.Column("content", sa.Text, default=""),
        sa.Column("round", sa.Integer, default=0),
        sa.Column("meta", json_t, default=dict),
        sa.Column("created_at", sa.DateTime, default=sa.func.utcnow()),
    )

    op.create_table(
        "discussion_syntheses",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("session_id", sa.Integer, sa.ForeignKey("discussion_sessions.id", ondelete="CASCADE"), index=True, nullable=False),
        sa.Column("decision", sa.Text, default=""),
        sa.Column("action_items", json_t, default=list),
        sa.Column("created_at", sa.DateTime, default=sa.func.utcnow()),
    )

    op.create_table(
        "review_comments",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("project_id", sa.Integer, sa.ForeignKey("projects.id", ondelete="CASCADE"), index=True),
        sa.Column("chapter_id", sa.Integer, sa.ForeignKey("chapters.id", ondelete="SET NULL"), index=True),
        sa.Column("version_id", sa.Integer, sa.ForeignKey("chapter_versions.id", ondelete="SET NULL"), index=True),
        sa.Column("reviewer_key", sa.String(80), default=""),
        sa.Column("severity", sa.String(20), default="info"),
        sa.Column("category", sa.String(40), default=""),
        sa.Column("anchor", sa.String(80), default=""),
        sa.Column("body", sa.Text, default=""),
        sa.Column("status", sa.String(20), default="open"),
        sa.Column("created_at", sa.DateTime, default=sa.func.utcnow()),
    )

    op.create_table(
        "review_settings",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("project_id", sa.Integer, sa.ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=False),
        sa.Column("auto_reader_review", sa.Boolean, default=True),
        sa.Column("auto_chief_triage", sa.Boolean, default=True),
        sa.Column("retention_days", sa.Integer, default=7),
        sa.Column("extra", json_t, default=dict),
        sa.Column("created_at", sa.DateTime, default=sa.func.utcnow()),
    )

    op.create_table(
        "chief_agent_sessions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("project_id", sa.Integer, sa.ForeignKey("projects.id", ondelete="CASCADE"), index=True),
        sa.Column("chapter_id", sa.Integer, sa.ForeignKey("chapters.id", ondelete="SET NULL"), index=True),
        sa.Column("topic", sa.String(240), default=""),
        sa.Column("status", sa.String(20), default="open"),
        sa.Column("extra", json_t, default=dict),
        sa.Column("created_at", sa.DateTime, default=sa.func.utcnow()),
    )

    op.create_table(
        "chief_agent_messages",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("session_id", sa.Integer, sa.ForeignKey("chief_agent_sessions.id", ondelete="CASCADE"), index=True, nullable=False),
        sa.Column("role", sa.String(40), default=""),
        sa.Column("speaker_key", sa.String(80), default=""),
        sa.Column("content", sa.Text, default=""),
        sa.Column("meta", json_t, default=dict),
        sa.Column("created_at", sa.DateTime, default=sa.func.utcnow()),
    )

    # ============================================================
    # 10) audit_logs
    # ============================================================
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("actor", sa.String(120), default=""),
        sa.Column("action", sa.String(120), default=""),
        sa.Column("target", sa.String(240), default=""),
        sa.Column("payload", json_t, default=dict),
        sa.Column("created_at", sa.DateTime, default=sa.func.utcnow(), index=True),
    )

    # ============================================================
    # 索引补强
    # ============================================================
    if is_pg:
        op.execute(
            "CREATE INDEX IF NOT EXISTS ix_agent_tasks_pending_pick "
            "ON agent_tasks (status, task_type, priority DESC, id) "
            "WHERE status = 'pending';"
        )
        op.execute(
            "CREATE INDEX IF NOT EXISTS ix_agent_tasks_lease "
            "ON agent_tasks (lease_expires_at) "
            "WHERE status = 'running';"
        )
        op.execute(
            "CREATE INDEX IF NOT EXISTS ix_study_runs_material_status "
            "ON study_runs (material_id, status);"
        )


def downgrade() -> None:
    # baseline 没有 down_revision, 实际回滚需要手工 DROP 表, 这里给空操作避免误删.
    # 业务回滚请走备份 + 新库重建.
    pass
