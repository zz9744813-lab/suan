"""P3: 项目记忆 (Raw + Stable) — 二次加工数据模型.

P3 spec 04 §6 §7: 把旧模式"MemoryUpdate → 直接写 Stable"改成
"MemoryUpdate → RawMemoryEntry → MemoryConsolidator → 去重/合并/
冲突识别 → 有冲突创建 DiscussionDecision → 裁决 → StableMemory".

5 张新表,跟旧的 memory_characters / memory_foreshadows /
memory_hard_facts 共存(后者保留作 legacy read,P3 §6 明确).

表清单:
  - RawMemoryEntry        原始记忆池(MemoryUpdateAgent 写入)
  - StableMemoryEntity    稳定实体(人物/地点/势力/物品/世界规则 共用)
  - StableCharacterState  稳定人物状态(随章节推进)
  - MemoryTimelineEvent   状态/事件时间线
  - DiscussionDecision    冲突裁决记录(DiscussionAgent 写入)

设计取舍 (跟 spec 对齐):
  - 7 类档案柜 (人物/伏笔/硬事实/地点/势力/物品/世界规则) 全部用
    StableMemoryEntity + entity_type 区分,不拆 7 张表 — 跟 P3 §3
    "档案柜" 视觉一致,但 schema 跟 P3 §7 严格相符.
  - P3 §11 写 "Planner/Draft/Continuity 只读 Stable",所以这 5 张表
    是新流水线的唯一目标. 旧 memory_characters 等表的写路径冻结
    (不删,只读).
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def _utcnow() -> datetime:
    return datetime.utcnow()


# ============================================================
# RawMemoryEntry (P3 §7.1) — MemoryUpdateAgent 写入的原始记忆池
# ============================================================
class RawMemoryEntry(Base):
    """The 'raw memory pool'.

    MemoryUpdateAgent runs after each chapter pipeline and writes
    one or more of these. status drives the consolidator's
    processing lifecycle:

      raw            just persisted, not yet seen by consolidator
      processed      consolidator consumed it, no merge/conflict needed
      merged         folded into a StableMemoryEntity (entity_id set)
      rejected       consolidator dropped it (duplicate / noise)
      needs_discussion consolidator couldn't decide, escalated to
                      DiscussionDecision
      decided        (set by DiscussionAgent apply step) — folded
                      into a stable row by the decision

    ``raw_payload`` carries the unnormalised LLM output (free-form
    JSON). ``source_quote`` and ``source_summary`` are the cited
    evidence — P3 §14 禁 4 要求"低置信度不能进 Stable",这里
    confidence 默认 0.5,Consolidator 阈值 0.7 才放行.
    """

    __tablename__ = "raw_memory_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True,
    )
    chapter_id: Mapped[int | None] = mapped_column(
        ForeignKey("chapters.id", ondelete="SET NULL"), default=None, index=True,
    )
    chapter_index: Mapped[int | None] = mapped_column(Integer, default=None, index=True)
    # The "shape" of the memory — e.g. "character_state", "foreshadow",
    # "hard_fact", "relationship". Drives the consolidator's
    # merge/conflict logic.
    entry_type: Mapped[str] = mapped_column(String(60), index=True)
    # The subject the entry is about — for character_state, the
    # character name; for foreshadow, the foreshadow name; etc.
    subject: Mapped[str] = mapped_column(String(200), index=True)
    # Lightweight (subject, predicate, object) triple for
    # rule-based dedup. Either may be null.
    predicate: Mapped[str | None] = mapped_column(String(80), default=None)
    object_value: Mapped[str | None] = mapped_column(Text, default=None)
    # The full LLM payload as-is. Kept verbatim (P3 §14 禁 5: 禁止
    # 删除 RawMemory, 留作追溯).
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    # Cited evidence.
    source_quote: Mapped[str | None] = mapped_column(Text, default=None)
    source_summary: Mapped[str | None] = mapped_column(Text, default=None)
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    agent_name: Mapped[str] = mapped_column(String(80), default="MemoryUpdateAgent")
    agent_step_id: Mapped[int | None] = mapped_column(Integer, default=None, index=True)
    status: Mapped[str] = mapped_column(String(20), default="raw", index=True)
    # When the consolidator last acted on this row.
    processed_at: Mapped[datetime | None] = mapped_column(default=None)
    # The stable entity this raw entry was merged into (only set
    # for status=merged / decided).
    merged_into_entity_id: Mapped[int | None] = mapped_column(
        ForeignKey("stable_memory_entities.id", ondelete="SET NULL"),
        default=None, index=True,
    )
    created_at: Mapped[datetime] = mapped_column(default=_utcnow, index=True)


# ============================================================
# StableMemoryEntity (P3 §7.2) — 7 类档案柜共用表
# ============================================================
class StableMemoryEntity(Base):
    """The 'stable memory' a Planner / Draft / Continuity agent
    is allowed to read. Drives the 7 archive cabinets in
    MemoryArchivePage.

    entity_type is one of:
      character / location / faction / item / world_rule /
      foreshadow / hard_fact

    The first five are 'long-lived objects' (人物/地点/势力/物品/
    世界规则); the last two (foreshadow, hard_fact) are
    'event-anchored facts' that still get a row in this table so
    the cabinet UI can render them through a single component.
    """

    __tablename__ = "stable_memory_entities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True,
    )
    # 7 cabinet values. Frontend color-maps each.
    entity_type: Mapped[str] = mapped_column(String(40), index=True)
    canonical_name: Mapped[str] = mapped_column(String(200), index=True)
    # All known name variants — P3 §12 示例: 苏瑶 / 苏瑶儿 / 瑶儿 /
    # 青云宗苏瑶 → canonical="苏瑶", aliases=["苏瑶儿","瑶儿",...].
    aliases: Mapped[list[str]] = mapped_column(JSON, default=list)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    # Free-form attributes (gender / age / faction for characters;
    # 面积 for locations; etc). Kept as JSON so each entity_type
    # can carry its own schema without a migration.
    profile: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    # 0.0..1.0 — P3 §14 禁 4 阈值: < 0.7 不进 Stable. Consolidator
    # sets this; manually editable.
    importance: Mapped[float] = mapped_column(Float, default=0.5)
    confidence: Mapped[float] = mapped_column(Float, default=0.7)
    # active (visible) / merged_into_X (cannibalised) /
    # deleted (soft-deleted, hidden from Stable reads)
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)
    first_chapter_index: Mapped[int | None] = mapped_column(Integer, default=None, index=True)
    last_chapter_index: Mapped[int | None] = mapped_column(Integer, default=None, index=True)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=_utcnow, onupdate=_utcnow)


# ============================================================
# StableCharacterState (P3 §7.3) — 人物当前状态, 跟章节挂钩
# ============================================================
class StableCharacterState(Base):
    """Snapshot of a character's current state. One row per
    'state change' (consolidator writes a new row when something
    material about a character shifts: location, goal, injury,
    etc.).

    ``evidence_entry_ids`` lists the RawMemoryEntry rows that
    triggered this state — P3 §14 禁 5 要求 RawMemory 永远保留,
    这里通过 FK 串起来而不是级联删.
    """

    __tablename__ = "stable_character_states"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True,
    )
    entity_id: Mapped[int] = mapped_column(
        ForeignKey("stable_memory_entities.id", ondelete="CASCADE"), index=True,
    )
    current_location: Mapped[str | None] = mapped_column(String(200), default=None)
    current_faction: Mapped[str | None] = mapped_column(String(120), default=None)
    current_goal: Mapped[str | None] = mapped_column(Text, default=None)
    emotion_state: Mapped[str | None] = mapped_column(String(200), default=None)
    injury_state: Mapped[str | None] = mapped_column(String(500), default=None)
    power_state: Mapped[str | None] = mapped_column(String(500), default=None)
    owned_items: Mapped[list[str]] = mapped_column(JSON, default=list)
    abilities: Mapped[list[str]] = mapped_column(JSON, default=list)
    secrets: Mapped[list[str]] = mapped_column(JSON, default=list)
    last_seen_chapter: Mapped[int | None] = mapped_column(Integer, default=None, index=True)
    evidence_entry_ids: Mapped[list[int]] = mapped_column(JSON, default=list)
    confidence: Mapped[float] = mapped_column(Float, default=0.7)
    updated_at: Mapped[datetime] = mapped_column(default=_utcnow, onupdate=_utcnow, index=True)


# ============================================================
# MemoryTimelineEvent (P3 §7.4) — 状态/事件时间线
# ============================================================
class MemoryTimelineEvent(Base):
    """One event on the project's memory timeline — "在第 N 章, 苏瑶
    受伤; 上一章她还在客栈" — the consolidator writes a new row
    whenever a state changes, and the archive page can show
    "this character moved from A to B at chapter N".

    ``before_state`` / ``after_state`` are the diff payloads (a
    free JSON dump of StableCharacterState at the moment of the
    change) so the timeline can render "was X, became Y" without
    the UI having to re-derive the diff.
    """

    __tablename__ = "memory_timeline_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True,
    )
    entity_id: Mapped[int | None] = mapped_column(
        ForeignKey("stable_memory_entities.id", ondelete="SET NULL"),
        default=None, index=True,
    )
    memory_type: Mapped[str] = mapped_column(String(60), index=True)
    chapter_id: Mapped[int | None] = mapped_column(
        ForeignKey("chapters.id", ondelete="SET NULL"), default=None,
    )
    chapter_index: Mapped[int | None] = mapped_column(Integer, default=None, index=True)
    event_title: Mapped[str] = mapped_column(String(300))
    event_summary: Mapped[str] = mapped_column(Text, default="")
    before_state: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=None)
    after_state: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=None)
    source_quote: Mapped[str | None] = mapped_column(Text, default=None)
    # The raw entry that surfaced this event (optional).
    source_entry_id: Mapped[int | None] = mapped_column(
        ForeignKey("raw_memory_entries.id", ondelete="SET NULL"),
        default=None,
    )
    # Agent name (MemoryConsolidator / DiscussionAgent) or "manual"
    # if a human entered it.
    created_by: Mapped[str] = mapped_column(String(80), default="MemoryConsolidatorAgent")
    created_at: Mapped[datetime] = mapped_column(default=_utcnow, index=True)


# ============================================================
# DiscussionDecision (P3 §7.5) — 冲突裁决记录
# ============================================================
class DiscussionDecision(Base):
    """A conflict the consolidator couldn't resolve on its own,
    escalated to the discussion room. The frontend shows a
    'pending' / 'running' / 'decided' / 'failed' badge and
    the final ``decision_payload`` (e.g. "merge_alias with
    canonical_name=苏瑶, aliases=[苏瑶儿, 瑶儿, ...]").

    P3 §5 核心原则: 冲突不单独暴露成冲突档案柜, 直接进入讨论室
    拿裁决结果 — 所以这表是 discussion room 的内存层, 7 柜
    (人物/伏笔/...) 不显示 "未决" 状态, 全部是"已决".
    """

    __tablename__ = "discussion_decisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True,
    )
    # 5 topic types per spec.
    topic_type: Mapped[str] = mapped_column(String(40), index=True)
    topic_title: Mapped[str] = mapped_column(String(300))
    # The RawMemoryEntry rows that triggered this conflict. Frontend
    # can show "查看 3 条原始记忆" by id-list lookup.
    raw_entry_ids: Mapped[list[int]] = mapped_column(JSON, default=list)
    related_entity_ids: Mapped[list[int]] = mapped_column(JSON, default=list)
    # pending / running / decided / failed
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    # The DiscussionAgent's verdict — populated when status=decided.
    # Schema varies by topic_type:
    #   duplicate_entity    → { "decision": "merge_alias", "canonical_name": "X", "aliases": [...] }
    #   field_conflict      → { "decision": "field_overwrite", "field": "age", "value": 18 }
    #   foreshadow_unclear  → { "decision": "keep_active" | "mark_dropped" }
    #   hard_fact_conflict  → { "decision": "overwrite" | "keep_existing", "value": "..." }
    #   relationship_conflict → { "decision": "set_relation", "relation": "师父", "weight": 0.8 }
    decision_payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=None)
    decision: Mapped[str | None] = mapped_column(String(60), default=None)
    reason: Mapped[str | None] = mapped_column(Text, default=None)
    # Which agent produced the verdict.
    decided_by_agent: Mapped[str | None] = mapped_column(String(80), default=None)
    # Link to the DiscussionSession row (R12) if the verdict was
    # reached via the discussion room (P0-FEAT-1's participants
    # pipeline). Optional — a fast-path DiscussionAgent may skip
    # the room and write the verdict directly.
    discussion_session_id: Mapped[int | None] = mapped_column(
        ForeignKey("discussion_sessions.id", ondelete="SET NULL"),
        default=None,
    )
    created_at: Mapped[datetime] = mapped_column(default=_utcnow, index=True)
    decided_at: Mapped[datetime | None] = mapped_column(default=None, index=True)
