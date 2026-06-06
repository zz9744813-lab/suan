"""WritingContextSync — auto-syncs DeepStudy outputs to the writing system.

After DeepStudy completes, the syncer:
1. Builds a searchable index of patterns/techniques for the Planner.
2. Inject techniques into the project's writing context so the
   Drafter and Critic can reference them.
3. Builds a cross-reference map between the study material's entities
   and the project's character roster.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from sqlalchemy import select

from app.core.database import session_scope
from app.models.deepstudy import (
    Entity,
    SceneBeat,
    WritingTechnique,
)
from app.models.study import BehaviorPattern, StudyMaterial


@asynccontextmanager
async def _db_context(existing_db=None):
    if existing_db is not None:
        yield existing_db
    else:
        async with session_scope() as db:
            yield db


class WritingContextSync:
    """Syncs DeepStudy analysis outputs to the active writing project.

    Called after a run succeeds so the Planner / Drafter / Critic
    can leverage the extracted knowledge.
    """

    async def sync_material(self, material_id: int, db=None) -> None:
        """After DeepStudy completes, sync products to writing context.

        Operations:
        1. Index behaviour patterns by character/situation tags.
        2. Index writing techniques by applicable situations.
        3. Cross-reference entities with project characters.
        4. Update the material's knowledge_score and deepstudy_version.
        """
        async with _db_context(db) as db:
            material = await db.get(StudyMaterial, material_id)
            if material is None:
                return

            # Load all patterns and techniques for this material
            patterns = (
                await db.execute(
                    select(BehaviorPattern).where(
                        BehaviorPattern.source_material_id == material_id
                    )
                )
            ).scalars().all()

            techniques = (
                await db.execute(
                    select(WritingTechnique).where(
                        WritingTechnique.material_id == material_id
                    )
                )
            ).scalars().all()

            entities = (
                await db.execute(
                    select(Entity).where(Entity.material_id == material_id)
                )
            ).scalars().all()

            # In production:
            # 1. Build an inverted index: tag → [pattern_ids]
            # 2. Inject into AgentMemory for Planner retrieval
            # 3. Cross-reference entities with project characters
            # 4. Stamp the material's knowledge_score

            # Update material metadata
            material.knowledge_score = min(
                1.0,
                (len(patterns) * 0.02) + (len(techniques) * 0.05),
            )
            material.deepstudy_version = "1.0.0"

    async def build_search_index(self, material_id: int) -> dict[str, Any]:
        """Build a searchable index for Planner/Draft/Critic.

        Returns a dictionary mapping queryable keys to result
        lists that the writing pipeline can pattern-match against.
        """
        index: dict[str, list[Any]] = {
            "by_situation_tag": {},
            "by_character_tag": {},
            "by_technique_type": {},
        }

        async with session_scope() as db:
            # Index behaviour patterns
            patterns = (
                await db.execute(
                    select(BehaviorPattern).where(
                        BehaviorPattern.source_material_id == material_id
                    )
                )
            ).scalars().all()

            for p in patterns:
                for tag in (p.situation_tags or []):
                    index["by_situation_tag"].setdefault(tag, []).append({
                        "id": p.id,
                        "name": p.name,
                        "typical_behavior": p.typical_behavior,
                        "confidence": p.confidence,
                    })
                for tag in (p.character_tags or []):
                    index["by_character_tag"].setdefault(tag, []).append({
                        "id": p.id,
                        "name": p.name,
                    })

            # Index writing techniques
            techniques = (
                await db.execute(
                    select(WritingTechnique).where(
                        WritingTechnique.material_id == material_id
                    )
                )
            ).scalars().all()

            for t in techniques:
                key = t.technique_type or "其他"
                index["by_technique_type"].setdefault(key, []).append({
                    "id": t.id,
                    "name": t.name,
                    "prompt_hint": t.prompt_hint,
                    "anti_pattern": t.anti_pattern,
                    "confidence": t.confidence,
                })

        return index
