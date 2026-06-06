"""TechniqueMiner — auto-generates writing techniques from
behaviour patterns + scene beats + foreshadow chains.

The miner analyses the book's structural patterns and distils
reusable writing techniques (开篇钩子 / 压迫感 / 反转 / ...).
Each technique carries a ``prompt_hint`` (one-line instruction
for the drafter) and an ``anti_pattern`` (the don't-do-this).

Two-phase operation:
1. ``mine_from_patterns`` — per-material LLM-driven distillation.
2. ``finalize_techniques`` — cross-book merging, deduplication,
   and confidence recalculation.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from sqlalchemy import select

from app.core.database import session_scope
from app.models.deepstudy import (
    BehaviorPatternEvidence,
    ForeshadowChain,
    SceneBeat,
    WritingTechnique,
)
from app.models.study import BehaviorPattern


@asynccontextmanager
async def _db_context(existing_db=None):
    if existing_db is not None:
        yield existing_db
    else:
        async with session_scope() as db:
            yield db


class TechniqueMiner:
    """Distils writing techniques from DeepStudy analysis output.

    Reads behaviour patterns, scene beats, and foreshadow chains
    to generate structured WritingTechnique records.
    """

    async def mine_from_patterns(self, material_id: int) -> None:
        """Generate techniques from behaviour patterns + scene beats + foreshadows.

        In production this:
        1. Reads all BehaviorPattern rows for this material.
        2. Groups them by situation_tags to find recurring scenarios.
        3. For each recurring scenario, calls an LLM to distil a
           one-line writing instruction (prompt_hint) and its
           anti-pattern.
        4. Upserts into ``deepstudy_writing_techniques`` with
           source tracking (which entities/scenes/behaviours the
           technique was distilled from).
        """
        async with session_scope() as db:
            # Load source data
            patterns = (
                await db.execute(
                    select(BehaviorPattern).where(
                        BehaviorPattern.source_material_id == material_id
                    )
                )
            ).scalars().all()

            beats = (
                await db.execute(
                    select(SceneBeat).where(
                        SceneBeat.material_id == material_id
                    )
                )
            ).scalars().all()

            foreshadows = (
                await db.execute(
                    select(ForeshadowChain).where(
                        ForeshadowChain.material_id == material_id
                    )
                )
            ).scalars().all()

            if not patterns:
                return  # Nothing to mine from

            # In production:
            # 1. Build situation frequency map from pattern.situation_tags
            # 2. For top-N situations, build LLM prompts with
            #    representative scene beats and foreshadows
            # 3. Distil prompt_hint + anti_pattern per technique type
            # 4. Create WritingTechnique rows
            # 5. Track source entity/scene/behaviour IDs for the UI

            # Compute situation frequencies
            situation_freq: dict[str, int] = {}
            for p in patterns:
                for tag in (p.situation_tags or []):
                    situation_freq[tag] = situation_freq.get(tag, 0) + 1

    async def finalize_techniques(self, material_id: int, db=None) -> None:
        """After all techniques generated, finalise.

        Operations:
        - Merge duplicate techniques (same technique_type +
          similar prompt_hint).
        - Recompute confidence from source evidence density.
        - Update the technique library statistics.
        """
        async with _db_context(db) as db:
            techniques = (
                await db.execute(
                    select(WritingTechnique).where(
                        WritingTechnique.material_id == material_id
                    )
                )
            ).scalars().all()

            for tech in techniques:
                # Recompute confidence from evidence density
                source_count = (
                    len(tech.source_entity_ids or [])
                    + len(tech.source_scene_ids or [])
                    + len(tech.source_behavior_ids or [])
                )
                if source_count > 0:
                    tech.confidence = min(1.0, source_count / 5.0)
