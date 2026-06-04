"""DeepStudy module (P0-DeepStudy / R25) — book-shelf + multi-agent
deep-study data model.

Why a new module instead of stuffing more rows into ``study.py``:
the spec (F:\\NovelForge_DeepStudy_书架式拆书与知识网络技术方案.md)
explicitly asks for a clean separation so the 2000-line study router
can keep doing its basic chapterize/character-extract job without
becoming unreadable. The old ``study_*`` and ``behavior_patterns``
tables stay — DeepStudy builds on top of them, not in place of them.

The 9 new tables are deliberately thin on FKs to ``graph_*``: the
DeepStudy knowledge graph is a separate concept (per-book, with
chapter / scene intermediate layers) and the spec says "graph_nodes /
graph_edges can keep the old graph, not force-migrate".

Schema overview
---------------

  study_materials (extended in study.py with study_status etc.)
      │
      ├── deepstudy_runs              (one per DeepStudy invocation)
      │     └── deepstudy_chapter_analyses
      ├── deepstudy_entities
      │     └── deepstudy_entity_mentions
      ├── deepstudy_scene_beats
      ├── deepstudy_relationships
      ├── deepstudy_foreshadow_chains
      ├── deepstudy_behavior_evidence
      └── deepstudy_writing_techniques

Common conventions
------------------
* Every row carries ``material_id`` so a delete on the material
  cascades cleanly. We don't add a layer of project_id here —
  project_id is on the material, and a query on the project is a
  join through material.
* All JSON blobs default to ``{}`` / ``[]`` so the worker can write
  them without a nullability dance. SQLite stores them as TEXT.
* ``confidence`` is a 0..1 float (Pydantic + JS both render this as
  a percentage with one decimal place).
* Status enums match the spec verbatim so the UI can hardcode
  the labels.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def _utcnow() -> datetime:
    return datetime.utcnow()


# ============================================================
# deepstudy_runs
# ============================================================
class StudyRun(Base):
    """One DeepStudy invocation against a material.

    The worker creates a row when the user clicks "启动 DeepStudy",
    and updates ``status`` / ``current_stage`` / ``progress`` /
    ``cost_usd`` as stages advance. ``mode`` decides which stages
    run (e.g. ``entities_only`` skips the relationship pass and is
    the typical "re-run after editing" entry point).
    """

    __tablename__ = "deepstudy_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    material_id: Mapped[int] = mapped_column(
        ForeignKey("study_materials.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[int | None] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"), default=None, index=True
    )
    # The DeepStudy state machine from the spec section 4.1:
    #   queued / running / paused / succeeded / failed / cancelled.
    # The *book*'s status (study_status) is a different field that
    # reflects the most-recent run's outcome; this row carries the
    # in-flight state of this run.
    status: Mapped[str] = mapped_column(String(20), default="queued")
    # mode: full / entities_only / relationships_only /
    #       behaviors_only / techniques_only / repair_failed
    mode: Mapped[str] = mapped_column(String(40), default="full")
    total_chapters: Mapped[int] = mapped_column(Integer, default=0)
    processed_chapters: Mapped[int] = mapped_column(Integer, default=0)
    # ``current_stage`` is a free-form string set by the worker
    # (chapter_profile / entity / scene_beat / relationship / ...).
    current_stage: Mapped[str | None] = mapped_column(String(40), default=None)
    # ``agent_plan`` is the Coordinator's run plan snapshot (which
    # stages, chapter ranges, concurrency). Useful for "为什么这
    # 轮跑得跟上次不一样" debugging.
    agent_plan: Mapped[dict | None] = mapped_column(JSON, default=None)
    # ``progress`` is a per-stage counter snapshot — see spec 4.1.
    progress: Mapped[dict | None] = mapped_column(JSON, default=None)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text, default=None)
    started_at: Mapped[datetime | None] = mapped_column(default=None)
    finished_at: Mapped[datetime | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=_utcnow, onupdate=_utcnow)

    chapter_analyses: Mapped[list["ChapterAnalysis"]] = relationship(
        back_populates="run", cascade="all, delete-orphan",
    )


# ============================================================
# deepstudy_chapter_analyses
# ============================================================
class ChapterAnalysis(Base):
    """One chapter's DeepStudy profile (ChapterProfilerAgent output).

    Per-chapter fields: a short summary, the narrative function
    (开篇立压迫 / 关系翻转 / 伏笔埋设 / ...), POV, tone, conflict
    type, reader hook, and the two numerical scores (pace_score /
    information_density). ``raw_result`` keeps the LLM's full JSON
    for audit and for downstream agents that want to re-read it.
    """

    __tablename__ = "deepstudy_chapter_analyses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("deepstudy_runs.id", ondelete="CASCADE"), index=True
    )
    material_id: Mapped[int] = mapped_column(
        ForeignKey("study_materials.id", ondelete="CASCADE"), index=True
    )
    chapter_id: Mapped[int] = mapped_column(
        ForeignKey("study_chapters.id", ondelete="CASCADE"), index=True
    )
    chapter_index: Mapped[int] = mapped_column(Integer)
    # Per-chapter status: pending / running / succeeded / failed / skipped
    status: Mapped[str] = mapped_column(String(20), default="pending")
    summary: Mapped[str] = mapped_column(Text, default="")
    narrative_function: Mapped[str | None] = mapped_column(String(80), default=None)
    pov: Mapped[str | None] = mapped_column(String(40), default=None)
    tone: Mapped[str | None] = mapped_column(String(40), default=None)
    conflict_type: Mapped[str | None] = mapped_column(String(60), default=None)
    reader_hook: Mapped[str | None] = mapped_column(Text, default=None)
    pace_score: Mapped[float | None] = mapped_column(Float, default=None)
    information_density: Mapped[float | None] = mapped_column(Float, default=None)
    raw_result: Mapped[dict | None] = mapped_column(JSON, default=None)
    error: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=_utcnow, onupdate=_utcnow)

    run: Mapped["StudyRun"] = relationship(back_populates="chapter_analyses")


# ============================================================
# deepstudy_entities
# ============================================================
class Entity(Base):
    """A unified entity (character / object / location / faction /
    concept / hard_fact / ...).

    Replaces the old study_characters + ad-hoc "object" rows. The
    spec lists 10 entity_types — see ``entity_type`` below. Profile
    is a free-form JSON blob whose shape depends on the type
    (人物 has role/motivation/abilities, 事物 has owner/function).
    """

    __tablename__ = "deepstudy_entities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    material_id: Mapped[int] = mapped_column(
        ForeignKey("study_materials.id", ondelete="CASCADE"), index=True
    )
    # entity_type enum: character / object / location / faction /
    #                   concept / rule / hard_fact / resource /
    #                   ability / secret
    entity_type: Mapped[str] = mapped_column(String(40), index=True)
    name: Mapped[str] = mapped_column(String(200), index=True)
    aliases: Mapped[list[str]] = mapped_column(JSON, default=list)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    # ``profile`` shape depends on entity_type (see spec 4.4).
    profile: Mapped[dict | None] = mapped_column(JSON, default=None)
    first_chapter_index: Mapped[int | None] = mapped_column(Integer, default=None)
    last_chapter_index: Mapped[int | None] = mapped_column(Integer, default=None)
    # 0..1; used by the UI for "importance" sizing on the graph.
    importance: Mapped[float] = mapped_column(Float, default=0.5)
    # 0..1; LLM's confidence. Low-confidence entities surface in the
    # "review_required" status flow.
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    # ``merge_key`` is the dedupe handle the merger uses to collapse
    # same-name / same-alias entities extracted from different
    # chapters. Format: ``material_id:entity_type:norm_name``.
    merge_key: Mapped[str | None] = mapped_column(String(200), default=None, index=True)
    created_by_agent: Mapped[str | None] = mapped_column(String(80), default=None)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=_utcnow, onupdate=_utcnow)

    mentions: Mapped[list["EntityMention"]] = relationship(
        back_populates="entity", cascade="all, delete-orphan",
    )


# ============================================================
# deepstudy_entity_mentions
# ============================================================
class EntityMention(Base):
    """One mention of an entity in a chapter (or scene) — keeps
    the original-quote evidence chain even after we've merged
    multiple mentions into a single entity.
    """

    __tablename__ = "deepstudy_entity_mentions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entity_id: Mapped[int] = mapped_column(
        ForeignKey("deepstudy_entities.id", ondelete="CASCADE"), index=True
    )
    material_id: Mapped[int] = mapped_column(
        ForeignKey("study_materials.id", ondelete="CASCADE"), index=True
    )
    chapter_id: Mapped[int] = mapped_column(
        ForeignKey("study_chapters.id", ondelete="CASCADE"), index=True
    )
    # ``scene_id`` references SceneBeat but we don't FK it (scenes
    # can be re-split). NULL means "this mention is chapter-level".
    scene_id: Mapped[int | None] = mapped_column(Integer, default=None)
    # 1-2 sentence quote, copied verbatim from the chapter text.
    quote: Mapped[str] = mapped_column(Text, default="")
    context_summary: Mapped[str | None] = mapped_column(Text, default=None)
    # mention_type: appearance / action / dialogue / memory /
    #               conflict / relationship / foreshadow / payoff
    mention_type: Mapped[str] = mapped_column(String(40), default="appearance")
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)

    entity: Mapped["Entity"] = relationship(back_populates="mentions")


# ============================================================
# deepstudy_scene_beats
# ============================================================
class SceneBeat(Base):
    """One beat inside a chapter — a (trigger, action, result)
    atomic unit that drives the chapter forward.

    Beats are the UI's middle layer between chapters and entities:
    the knowledge graph renders chapters → beats → entities as a
    three-level hierarchy. ``involved_entity_ids`` is a list (not
    a relationship) to keep the write path simple and to allow
    the merger to update without touching the beat row.
    """

    __tablename__ = "deepstudy_scene_beats"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    material_id: Mapped[int] = mapped_column(
        ForeignKey("study_materials.id", ondelete="CASCADE"), index=True
    )
    chapter_id: Mapped[int] = mapped_column(
        ForeignKey("study_chapters.id", ondelete="CASCADE"), index=True
    )
    chapter_index: Mapped[int] = mapped_column(Integer)
    # ``beat_index`` is the 1-based ordinal inside the chapter —
    # lets the UI render beats in narrative order without a sort
    # on confidence / importance.
    beat_index: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(200), default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    # scene_type: 铺垫 / 冲突 / 试探 / 压迫 / 反击 / 交易 / 战斗 /
    #             揭秘 / 升级 / 转折 / 伏笔 / 回收 / 收束 / 钩子
    scene_type: Mapped[str] = mapped_column(String(40), default="铺垫")
    conflict: Mapped[str | None] = mapped_column(Text, default=None)
    trigger: Mapped[str | None] = mapped_column(Text, default=None)
    action: Mapped[str | None] = mapped_column(Text, default=None)
    result: Mapped[str | None] = mapped_column(Text, default=None)
    reader_emotion: Mapped[str | None] = mapped_column(String(120), default=None)
    involved_entity_ids: Mapped[list[int]] = mapped_column(JSON, default=list)
    evidence_quotes: Mapped[list[str]] = mapped_column(JSON, default=list)
    importance: Mapped[float] = mapped_column(Float, default=0.5)
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    raw_result: Mapped[dict | None] = mapped_column(JSON, default=None)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)


# ============================================================
# deepstudy_relationships
# ============================================================
class Relationship(Base):
    """A semantic (not co-occurrence) relationship between two
    entities. ``relation_type`` is the spec's enum (family / rival
    / enemy / ...), ``relation_label`` is the LLM's free-form
    Chinese label (兄弟镜像 / 公开对立 / ...). ``direction`` is
    one of ``bidirectional`` / ``a_to_b`` / ``b_to_a`` so a one-way
    "师父" relation is recorded correctly.
    """

    __tablename__ = "deepstudy_relationships"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    material_id: Mapped[int] = mapped_column(
        ForeignKey("study_materials.id", ondelete="CASCADE"), index=True
    )
    source_entity_id: Mapped[int] = mapped_column(
        ForeignKey("deepstudy_entities.id", ondelete="CASCADE"), index=True
    )
    target_entity_id: Mapped[int] = mapped_column(
        ForeignKey("deepstudy_entities.id", ondelete="CASCADE"), index=True
    )
    # Spec enum: family / master_disciple / enemy / rival / ally /
    # lover / friend / faction_member / owner / user_of_item /
    # knows_secret / uses / protects / betrays / suppresses /
    # tests / depends_on
    relation_type: Mapped[str] = mapped_column(String(40), index=True)
    relation_label: Mapped[str] = mapped_column(String(200), default="")
    # direction: bidirectional / a_to_b / b_to_a
    direction: Mapped[str] = mapped_column(String(20), default="bidirectional")
    # 0..1; higher = stronger evidence / more scenes support it.
    strength: Mapped[float] = mapped_column(Float, default=0.5)
    # The first / last chapter where this relation is observed.
    chapter_start: Mapped[int | None] = mapped_column(Integer, default=None)
    chapter_end: Mapped[int | None] = mapped_column(Integer, default=None)
    # status enum: candidate / confirmed / low_confidence /
    #              manual_review / rejected
    status: Mapped[str] = mapped_column(String(20), default="candidate")
    evidence_quotes: Mapped[list[str]] = mapped_column(JSON, default=list)
    # A human-readable "how the relationship changed" sentence
    # (e.g. "从表层兄弟关系转为资质与资源压力下的竞争关系").
    change_summary: Mapped[str | None] = mapped_column(Text, default=None)
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    created_by_agent: Mapped[str] = mapped_column(String(80), default="")
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=_utcnow, onupdate=_utcnow)


# ============================================================
# deepstudy_foreshadow_chains
# ============================================================
class ForeshadowChain(Base):
    """A multi-chapter foreshadow chain (plant → advance → payoff),
    not a single isolated event. ``evidence`` is a list of
    {chapter, type, quote, summary} dicts that the LLM curates
    across the whole book so the writer can see "this is the
    chain, here's the payoff".
    """

    __tablename__ = "deepstudy_foreshadow_chains"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    material_id: Mapped[int] = mapped_column(
        ForeignKey("study_materials.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(200), default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    # foreshadow_type: 物品 / 信息 / 人物身世 / 关系 / 事件 / 规则
    foreshadow_type: Mapped[str] = mapped_column(String(40), default="事件")
    planted_chapter: Mapped[int | None] = mapped_column(Integer, default=None)
    # Chapters where the foreshadow was advanced (between plant
    # and payoff). Empty list for short arcs.
    advanced_chapters: Mapped[list[int]] = mapped_column(JSON, default=list)
    payoff_chapter: Mapped[int | None] = mapped_column(Integer, default=None)
    # status enum: planted / advanced / paid_off / abandoned /
    #              unclear
    status: Mapped[str] = mapped_column(String(20), default="planted")
    related_entity_ids: Mapped[list[int]] = mapped_column(JSON, default=list)
    # evidence example:
    #   [{"chapter": 3, "type": "planted", "quote": "...",
    #     "summary": "首次出现但意义不明"}, ...]
    evidence: Mapped[list[dict]] = mapped_column(JSON, default=list)
    reader_effect: Mapped[str | None] = mapped_column(Text, default=None)
    writing_function: Mapped[str | None] = mapped_column(Text, default=None)
    importance: Mapped[float] = mapped_column(Float, default=0.5)
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=_utcnow, onupdate=_utcnow)


# ============================================================
# deepstudy_behavior_evidence
# ============================================================
class BehaviorPatternEvidence(Base):
    """One evidence row anchoring a BehaviorPattern to a real scene.

    The spec is explicit: behaviour patterns must be backed by
    per-chapter evidence, not a vague summary. This table is the
    evidence layer. Pattern rows themselves live in the existing
    ``behavior_patterns`` table; we keep that name to avoid
    breaking the drafter's tag-based lookup.
    """

    __tablename__ = "deepstudy_behavior_evidence"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    behavior_pattern_id: Mapped[int] = mapped_column(
        ForeignKey("behavior_patterns.id", ondelete="CASCADE"), index=True
    )
    material_id: Mapped[int] = mapped_column(
        ForeignKey("study_materials.id", ondelete="CASCADE"), index=True
    )
    chapter_id: Mapped[int] = mapped_column(
        ForeignKey("study_chapters.id", ondelete="CASCADE"), index=True
    )
    scene_id: Mapped[int | None] = mapped_column(Integer, default=None)
    character_entity_id: Mapped[int | None] = mapped_column(
        ForeignKey("deepstudy_entities.id", ondelete="SET NULL"), default=None
    )
    # ``situation`` answers "in what kind of scene did this happen"
    # and ``trigger`` answers "what kicked it off". Together they
    # let the writer search "主角被公开压迫时通常怎么反应".
    situation: Mapped[str] = mapped_column(Text, default="")
    trigger: Mapped[str] = mapped_column(Text, default="")
    behavior: Mapped[str] = mapped_column(Text, default="")
    dialogue_style: Mapped[str | None] = mapped_column(Text, default=None)
    result: Mapped[str] = mapped_column(Text, default="")
    evidence_quote: Mapped[str] = mapped_column(Text, default="")
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)


# ============================================================
# deepstudy_writing_techniques
# ============================================================
class WritingTechnique(Base):
    """A reusable writing technique distilled from one or more
    books. ``prompt_hint`` is the one-line writing instruction
    the drafter injects into the LLM prompt when the situation
    matches ``applicable_situations``. ``anti_pattern`` is the
    don't-do-this companion (e.g. "不能只让主角忍, 否则会变
    成憋屈"). Together they form a tip card the drafter can
    pattern-match against.
    """

    __tablename__ = "deepstudy_writing_techniques"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    material_id: Mapped[int] = mapped_column(
        ForeignKey("study_materials.id", ondelete="SET NULL"), default=None, index=True
    )
    name: Mapped[str] = mapped_column(String(200), default="")
    # technique_type enum: 开篇钩子 / 人物塑造 / 压迫感 / 反转 /
    #                     爽点 / 伏笔埋设 / 伏笔回收 / 信息差 /
    #                     关系推进 / 节奏控制 / 战斗设计 /
    #                     对话设计 / 世界观展示
    technique_type: Mapped[str] = mapped_column(String(40), index=True)
    summary: Mapped[str] = mapped_column(Text, default="")
    applicable_genres: Mapped[list[str]] = mapped_column(JSON, default=list)
    applicable_situations: Mapped[list[str]] = mapped_column(JSON, default=list)
    # Traceability back to the source entities / scenes / behaviors
    # the technique was distilled from. UI shows the source so the
    # writer can click through to the original evidence.
    source_entity_ids: Mapped[list[int]] = mapped_column(JSON, default=list)
    source_scene_ids: Mapped[list[int]] = mapped_column(JSON, default=list)
    source_behavior_ids: Mapped[list[int]] = mapped_column(JSON, default=list)
    evidence_quotes: Mapped[list[str]] = mapped_column(JSON, default=list)
    # ``prompt_hint`` is the actual one-line writing instruction.
    # Example: "当你要写「弱势主角被公开压迫但不能立刻反击」
    # 的桥段时, 先让主角表面接受规则, 再通过一个不起眼的硬事
    # 实保存筹码, 最后在章末给出反制暗示, 形成追读钩子."
    prompt_hint: Mapped[str] = mapped_column(Text, default="")
    # ``anti_pattern`` is the "don't" — e.g. "不能只让主角忍, 否
    # 则会变成憋屈". Keeps the technique from being mis-applied.
    anti_pattern: Mapped[str | None] = mapped_column(Text, default=None)
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    # ``times_used`` is the runtime counter — bumped by the drafter
    # each time it injects this technique. Lets the user see which
    # techniques have actually influenced their draft.
    times_used: Mapped[int] = mapped_column(Integer, default=0)
    last_used_at: Mapped[datetime | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=_utcnow, onupdate=_utcnow)
