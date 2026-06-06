"""BehaviorPatternMiner — auto-generates behaviour patterns from
entity + event + scene data.

Reads Entity, Event/SuccessEvent, SceneBeat, and Relationship data
and produces structured BehaviorPatternEvidence records that anchor
the old ``behavior_patterns`` table to real chapters.

The miner is called chapter-by-chapter and then consolidated at the
end for whole-book patterns.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from sqlalchemy import select

from app.core.database import session_scope
from app.models.deepstudy import (
    BehaviorPatternEvidence,
    Entity,
    Relationship,
    SceneBeat,
)
from app.models.study import BehaviorPattern, StudyChapter


@asynccontextmanager
async def _db_context(existing_db=None):
    if existing_db is not None:
        yield existing_db
    else:
        async with session_scope() as db:
            yield db


class BehaviorPatternMiner:
    """Mines behaviour patterns from DeepStudy output data.

    Two-phase operation:
    1. ``mine_batch`` — per-chapter (or per-chapter-range) LLM-driven
       extraction of situation/trigger/behaviour/result tuples.
    2. ``finalize_book_patterns`` — cross-chapter consolidation into
       reusable BehaviorPattern cards with character/situation tags.
    """

    async def mine_batch(
        self,
        material_id: int,
        chapter_range: tuple[int, int] | None = None,
    ) -> None:
        """Auto-mine behaviour patterns from extracted data.

        For each chapter in the range:
        - Reads the chapter's entities, scene beats, and relationships.
        - In production, sends the data to an LLM agent that returns
          structured BehaviorPatternEvidence records.
        - Auto-upserts into the ``behavior_patterns`` and
          ``deepstudy_behavior_evidence`` tables.

        Args:
            material_id: The study material to mine.
            chapter_range: Optional (start, end) 1-based chapter range.
        """
        async with session_scope() as db:
            # Load chapters in range
            chap_query = select(StudyChapter).where(
                StudyChapter.material_id == material_id
            ).order_by(StudyChapter.chapter_index)

            if chapter_range is not None:
                lo, hi = chapter_range
                chap_query = chap_query.where(
                    StudyChapter.chapter_index >= lo,
                    StudyChapter.chapter_index <= hi,
                )

            chapters = (await db.execute(chap_query)).scalars().all()

            for chapter in chapters:
                await self._mine_chapter(db, material_id, chapter)

    async def _mine_chapter(self, db, material_id: int, chapter) -> None:
        """Mine behaviour patterns from a single chapter.

        In production this calls an LLM to analyse the scene beats
        and produce structured evidence rows. For now, it's a stub
        that verifies data availability.
        """
        # Verify we have scene beats for this chapter
        beats = (
            await db.execute(
                select(SceneBeat).where(
                    SceneBeat.material_id == material_id,
                    SceneBeat.chapter_id == chapter.id,
                )
            )
        ).scalars().all()

        if not beats:
            return  # No scene data to mine from

        # In production:
        # 1. Build a prompt with chapter text + scene beats + entities
        # 2. Call LLM to extract behaviour patterns
        # 3. Create BehaviorPattern rows with character_tags,
        #    situation_tags from extracted data
        # 4. Create BehaviorPatternEvidence rows linking back to
        #    the source scene/entity/quote

    async def finalize_book_patterns(self, material_id: int, db=None) -> None:
        """After all chapters mined, consolidate patterns.

        Operations:
        - Merge similar patterns (same character_tags + situation_tags
          but different chapters).
        - Recompute confidence from evidence density.
        - Remove low-confidence patterns.
        - Generate global pattern statistics.
        """
        async with _db_context(db) as db:
            # Load all patterns for this material
            patterns = (
                await db.execute(
                    select(BehaviorPattern).where(
                        BehaviorPattern.source_material_id == material_id
                    )
                )
            ).scalars().all()

            for pattern in patterns:
                # Count evidence rows for confidence recalculation
                ev_count = (
                    await db.execute(
                        select(BehaviorPatternEvidence).where(
                            BehaviorPatternEvidence.behavior_pattern_id == pattern.id,
                            BehaviorPatternEvidence.material_id == material_id,
                        )
                    )
                ).scalars().all()

                if len(ev_count) == 0:
                    pattern.confidence = 0.0
                else:
                    # Scale confidence by evidence count (up to 3+ = 1.0)
                    pattern.confidence = min(1.0, len(ev_count) / 3.0)
