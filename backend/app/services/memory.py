"""Memory service: update character states and hard facts from a final chapter.

Per spec §4 / §8, MemoryUpdateAgent is *only* allowed to extract facts from
the confirmed text — never to invent new bible rules.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.memory import (
    MemoryCharacter,
    MemoryCharacterState,
    MemoryForeshadow,
    MemoryHardFact,
)
from app.models.project import Chapter


@dataclass
class MemoryUpdateResult:
    character_updates: int
    foreshadow_updates: int
    hard_fact_additions: int


class MemoryService:
    async def update_from_chapter(
        self,
        db: AsyncSession,
        *,
        chapter: Chapter,
        final_text: str,
    ) -> MemoryUpdateResult:
        # 1) Touch last_seen_chapter on every character
        chars = (
            await db.execute(
                select(MemoryCharacter)
                .where(MemoryCharacter.project_id == chapter.project_id)
            )
        ).scalars().all()

        # crude extraction: sentences containing the character name => "present"
        updated = 0
        for c in chars:
            if c.name and c.name in final_text:
                # build a minimal state snapshot
                state = MemoryCharacterState(
                    character_id=c.id,
                    project_id=chapter.project_id,
                    chapter_no=chapter.chapter_no,
                    last_seen_chapter=chapter.chapter_no,
                    current_location=_extract_location(final_text, c.name),
                    emotion_state=_extract_emotion(final_text, c.name),
                    injury_state=_extract_injury(final_text, c.name),
                    current_goal=None,
                )
                db.add(state)
                updated += 1

        # 2) Look for the keyword "埋下" / "伏笔" to plant foreshadows
        f_count = 0
        for line in final_text.splitlines():
            m = re.search(r"埋下[伏线笔]?[：:]?\s*([\u4e00-\u9fff、，,\s]{4,40})", line)
            if m:
                name = m.group(1).strip().rstrip("。，,")
                if not name:
                    continue
                db.add(
                    MemoryForeshadow(
                        project_id=chapter.project_id,
                        name=name[:120],
                        summary=line.strip()[:300],
                        planted_chapter=chapter.chapter_no,
                        status="active",
                        importance=0.5,
                    )
                )
                f_count += 1

        # 3) Hard facts: "【硬设定】" or "本章确定：" prefixes
        hf_count = 0
        for line in final_text.splitlines():
            for prefix in ("【硬设定】", "本章确定：", "【设定】"):
                if prefix in line:
                    fact = line.split(prefix, 1)[1].strip()
                    if fact:
                        db.add(
                            MemoryHardFact(
                                project_id=chapter.project_id,
                                category="auto",
                                fact=fact[:500],
                                source_chapter=chapter.chapter_no,
                            )
                        )
                        hf_count += 1
                        break

        await db.flush()
        return MemoryUpdateResult(
            character_updates=updated,
            foreshadow_updates=f_count,
            hard_fact_additions=hf_count,
        )


def _extract_location(text: str, name: str) -> str | None:
    for sent in re.split(r"[。！？\n]", text):
        if name in sent and ("在" in sent or "来到" in sent or "赶回" in sent):
            return sent.strip()[:200]
    return None


def _extract_emotion(text: str, name: str) -> str | None:
    emotions = ("愤怒", "悲伤", "压抑", "喜悦", "恐惧", "焦虑", "冷静", "决然", "纠结", "犹豫")
    for sent in re.split(r"[。！？\n]", text):
        if name in sent:
            for e in emotions:
                if e in sent:
                    return e
    return None


def _extract_injury(text: str, name: str) -> str | None:
    for sent in re.split(r"[。！？\n]", text):
        if name in sent and ("受伤" in sent or "伤势" in sent or "伤" in sent):
            return sent.strip()[:200]
    return None
