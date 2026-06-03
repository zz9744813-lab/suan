"""ContextCompiler: assembles the per-chapter writing context package.

This is spec §9.1. It reads memory tables and produces a dict that gets
fed into Planner / Draft / Critic / Rewrite prompts as named inputs.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.memory import (
    MemoryCharacter,
    MemoryCharacterState,
    MemoryForeshadow,
    MemoryHardFact,
)
from app.models.project import Chapter, Outline, Project
from app.models.task import WorkerPolicy


@dataclass
class ChapterContext:
    chapter_id: int
    project_id: int
    chapter_no: int
    title: str
    target_word_count: int
    prior_chapter: dict[str, Any] | None
    recent_summaries: list[dict[str, Any]]
    characters_present: list[dict[str, Any]]
    character_states: list[dict[str, Any]]
    active_foreshadows: list[dict[str, Any]]
    hard_facts: list[str]
    outline_summary: str | None
    policy: dict[str, Any]
    detail_guard_reminders: list[str]


class ContextCompiler:
    async def compile(
        self,
        db: AsyncSession,
        *,
        chapter: Chapter,
        policy: WorkerPolicy,
    ) -> ChapterContext:
        project = await db.get(Project, chapter.project_id)
        if project is None:
            raise ValueError(f"Project {chapter.project_id} missing")

        # prior + recent chapters
        recent = (
            await db.execute(
                select(Chapter)
                .where(Chapter.project_id == chapter.project_id, Chapter.chapter_no < chapter.chapter_no)
                .order_by(Chapter.chapter_no.desc())
                .limit(5)
            )
        ).scalars().all()
        # P0-1 fix: list comprehension previously called the (sync) helper
        # inside an async context, which returned a coroutine instead of the
        # summary text and surfaced as
        #   AttributeError: 'coroutine' object has no attribute 'scalar_one_or_none'
        # at chapter 2+. Build the list with a plain loop so we can `await`
        # each helper call.
        recent_summaries: list[dict[str, Any]] = []
        for c in reversed(recent):
            recent_summaries.append(
                {
                    "chapter_no": c.chapter_no,
                    "title": c.title,
                    "summary": await _first_version_summary(db, c.id),
                }
            )
        prior = recent_summaries[-1] if recent_summaries else None

        # outline for this chapter
        outline_row = None
        if chapter.outline_id:
            outline_row = await db.get(Outline, chapter.outline_id)

        # characters + latest states
        characters = (
            await db.execute(
                select(MemoryCharacter)
                .options(selectinload(MemoryCharacter.states))
                .where(MemoryCharacter.project_id == chapter.project_id)
            )
        ).scalars().all()
        char_present: list[dict[str, Any]] = []
        char_states: list[dict[str, Any]] = []
        for c in characters:
            latest = c.states[0] if c.states else None
            base = {
                "id": c.id,
                "name": c.name,
                "aliases": c.aliases,
                "role": c.role,
                "tags": c.tags,
            }
            char_present.append(base)
            if latest:
                char_states.append(
                    {
                        "name": c.name,
                        "chapter_no": latest.chapter_no,
                        "current_location": latest.current_location,
                        "current_faction": latest.current_faction,
                        "current_goal": latest.current_goal,
                        "injury_state": latest.injury_state,
                        "emotion_state": latest.emotion_state,
                        "secrets": latest.secrets,
                        "misunderstandings": latest.misunderstandings,
                        "relationships": latest.relationships,
                        "owned_items": latest.owned_items,
                        "abilities": latest.abilities,
                        "last_seen_chapter": latest.last_seen_chapter,
                    }
                )

        # active foreshadows
        fores = (
            await db.execute(
                select(MemoryForeshadow)
                .where(
                    MemoryForeshadow.project_id == chapter.project_id,
                    MemoryForeshadow.status == "active",
                )
                .order_by(MemoryForeshadow.importance.desc())
                .limit(20)
            )
        ).scalars().all()
        active_fs = [
            {
                "name": f.name,
                "summary": f.summary,
                "planted_chapter": f.planted_chapter,
                "expected_payoff_chapter": f.expected_payoff_chapter,
                "importance": f.importance,
                "related_characters": f.related_characters,
                "related_items": f.related_items,
                "related_main_plot": f.related_main_plot,
            }
            for f in fores
        ]

        hard_facts_rows = (
            await db.execute(
                select(MemoryHardFact)
                .where(MemoryHardFact.project_id == chapter.project_id)
                .order_by(MemoryHardFact.id.desc())
                .limit(50)
            )
        ).scalars().all()
        hard_facts = [f"{f.category}: {f.fact}" for f in hard_facts_rows]

        # heuristic: this chapter should pay off fores with expected_payoff within ±1
        must_advance: list[str] = []
        for f in fores:
            exp = f.expected_payoff_chapter
            if exp is not None and abs(exp - chapter.chapter_no) <= 1:
                must_advance.append(
                    f"{f.name}（计划回收章节 {exp}，请本章推进或回收）"
                )

        reminders = self._build_detail_guard_reminders(char_states, prior, must_advance)

        return ChapterContext(
            chapter_id=chapter.id,
            project_id=chapter.project_id,
            chapter_no=chapter.chapter_no,
            title=chapter.title,
            target_word_count=chapter.target_word_count,
            prior_chapter=prior,
            recent_summaries=recent_summaries,
            characters_present=char_present,
            character_states=char_states,
            active_foreshadows=active_fs,
            hard_facts=hard_facts,
            outline_summary=outline_row.summary if outline_row else None,
            policy={
                "pass_score": policy.pass_score,
                "max_rewrite_rounds": policy.max_rewrite_rounds,
                "daily_word_goal": policy.daily_word_goal,
                "daily_budget_usd": policy.daily_budget_usd,
                "discussion_policy": policy.discussion_policy,
            },
            detail_guard_reminders=reminders,
        )

    def _build_detail_guard_reminders(
        self,
        char_states: list[dict[str, Any]],
        prior: dict[str, Any] | None,
        must_advance: list[str],
    ) -> list[str]:
        notes: list[str] = []
        for st in char_states:
            if st.get("injury_state"):
                notes.append(
                    f"{st['name']} 当前伤势：{st['injury_state']}，本章写作必须遵守。"
                )
            if st.get("secrets"):
                for s in st["secrets"]:
                    notes.append(
                        f"{st['name']} 仍有未公开秘密：{s}；本章未揭示前，旁人不可能知道。"
                    )
            if st.get("emotion_state"):
                notes.append(
                    f"{st['name']} 当前情绪：{st['emotion_state']}，对白与动作需保持一致。"
                )
        if prior:
            notes.append(
                f"上一章结尾：{prior.get('title')}（第 {prior.get('chapter_no')} 章）。本章必须承接。"
            )
        for m in must_advance:
            notes.append(f"伏笔提醒：{m}")
        return notes

    def to_prompt_inputs(self, ctx: ChapterContext) -> dict[str, Any]:
        return {
            "chapter_id": ctx.chapter_id,
            "project_id": ctx.project_id,
            "chapter_no": ctx.chapter_no,
            "title": ctx.title,
            "target_word_count": ctx.target_word_count,
            "prior_chapter": ctx.prior_chapter or "(无前章，这是第一章)",
            "recent_summaries": ctx.recent_summaries,
            "characters_present": ctx.characters_present,
            "character_states": ctx.character_states,
            "active_foreshadows": ctx.active_foreshadows,
            "hard_facts": ctx.hard_facts,
            "outline_summary": ctx.outline_summary or "(无大纲)",
            "policy": ctx.policy,
            "detail_guard_reminders": ctx.detail_guard_reminders,
        }


async def _first_version_summary(db: AsyncSession, chapter_id: int) -> str | None:
    """Return the most recent ChapterVersion summary for ``chapter_id``.

    P0-1 fix: this used to be a synchronous function that called
    ``db.execute`` (the AsyncSession API requires ``await``). At chapter
    2+ the list comprehension in :meth:`ContextCompiler.compile` would
    receive coroutine objects, not strings, and the next access would
    blow up with ``AttributeError: 'coroutine' object has no attribute
    'scalar_one_or_none'``.
    """
    from app.models.project import ChapterVersion

    ver = (
        await db.execute(
            select(ChapterVersion)
            .where(ChapterVersion.chapter_id == chapter_id)
            .order_by(ChapterVersion.version_no.desc())
            # R15 fix: cap at 1 row. ``scalar_one_or_none`` raises
            # ``MultipleResultsFound`` once a chapter accumulates 2+ versions
            # (e.g. chapter 3 has draft + rewrite_1 + final). The "most
            # recent" semantics is preserved by the ``order_by`` above.
            .limit(1)
        )
    ).scalar_one_or_none()

    if ver is None:
        return None

    if ver.summary:
        return ver.summary
    if ver.content:
        return ver.content[:200] + "..."
    return None


_context_compiler_singleton: ContextCompiler | None = None


def get_context_compiler() -> ContextCompiler:
    global _context_compiler_singleton
    if _context_compiler_singleton is None:
        _context_compiler_singleton = ContextCompiler()
    return _context_compiler_singleton
