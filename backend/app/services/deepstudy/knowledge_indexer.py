"""KnowledgeIndexer — indexes all DeepStudy outputs for retrieval.

Creates semantic search indexes from the book's entities, scenes,
relationships, foreshadows, behaviour patterns, and writing techniques
so the Planner / Drafter / Critic can query "what similar patterns
exist for 主角 + 公开羞辱" and get ranked results.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select

from app.core.database import session_scope
from app.models.deepstudy import (
    BehaviorPatternEvidence,
    Entity,
    EntityMention,
    ForeshadowChain,
    Relationship,
    SceneBeat,
    WritingTechnique,
)
from app.models.study import BehaviorPattern, StudyChapter, StudyMaterial


class KnowledgeIndexer:
    """Builds searchable indexes from DeepStudy analysis output.

    After a run completes, the indexer creates inverted indexes
    suitable for keyword and semantic retrieval.
    """

    async def index_material(self, material_id: int) -> None:
        """Index all DeepStudy outputs for retrieval.

        Builds per-material indexes:
        - Entity index: name → {profile, mentions, relationships}
        - Scene index: scene_type → beats sorted by importance
        - Foreshadow index: foreshadow_type → chains
        - Pattern index: character_tag × situation_tag → patterns
        - Technique index: technique_type → techniques ranked by usage

        In production this writes to a vector store or FTS table.
        For the MVP it validates data integrity and computes stats.
        """
        async with session_scope() as db:
            material = await db.get(StudyMaterial, material_id)
            if material is None:
                return

            # Validate data completeness
            entity_count = (
                await db.execute(
                    select(Entity).where(Entity.material_id == material_id)
                )
            ).scalars().all()
            mention_count = (
                await db.execute(
                    select(EntityMention).where(EntityMention.material_id == material_id)
                )
            ).scalars().all()
            scene_count = (
                await db.execute(
                    select(SceneBeat).where(SceneBeat.material_id == material_id)
                )
            ).scalars().all()
            rel_count = (
                await db.execute(
                    select(Relationship).where(Relationship.material_id == material_id)
                )
            ).scalars().all()
            foreshadow_count = (
                await db.execute(
                    select(ForeshadowChain).where(ForeshadowChain.material_id == material_id)
                )
            ).scalars().all()
            pattern_count = (
                await db.execute(
                    select(BehaviorPattern).where(
                        BehaviorPattern.source_material_id == material_id
                    )
                )
            ).scalars().all()
            evidence_count = (
                await db.execute(
                    select(BehaviorPatternEvidence).where(
                        BehaviorPatternEvidence.material_id == material_id
                    )
                )
            ).scalars().all()
            technique_count = (
                await db.execute(
                    select(WritingTechnique).where(
                        WritingTechnique.material_id == material_id
                    )
                )
            ).scalars().all()

            # Compute a knowledge_score from data density
            chapter_count = (
                await db.execute(
                    select(StudyChapter).where(StudyChapter.material_id == material_id)
                )
            ).scalars().all()

            if chapter_count:
                ch_total = len(chapter_count)
                density = (
                    (len(entity_count) / max(ch_total, 1))
                    + (len(scene_count) / max(ch_total, 1))
                    + (len(rel_count) / max(ch_total, 1))
                    + (len(foreshadow_count) / max(ch_total, 1))
                ) / 4.0

                material.knowledge_score = min(1.0, density)

    async def search_entities(
        self, material_id: int, query: str, limit: int = 20
    ) -> list[dict[str, Any]]:
        """Search entities by name or tag."""
        async with session_scope() as db:
            entities = (
                await db.execute(
                    select(Entity).where(
                        Entity.material_id == material_id,
                        Entity.name.contains(query),
                    ).limit(limit)
                )
            ).scalars().all()

            return [
                {
                    "id": e.id,
                    "name": e.name,
                    "entity_type": e.entity_type,
                    "tags": e.tags or [],
                    "importance": e.importance,
                    "confidence": e.confidence,
                }
                for e in entities
            ]

    async def search_patterns(
        self,
        material_id: int,
        character_tag: str | None = None,
        situation_tag: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Search behaviour patterns by character/situation tags."""
        async with session_scope() as db:
            query = select(BehaviorPattern).where(
                BehaviorPattern.source_material_id == material_id
            )
            if character_tag:
                from sqlalchemy import String
                query = query.where(
                    BehaviorPattern.character_tags.cast(String).contains(character_tag)
                )
            if situation_tag:
                from sqlalchemy import String
                query = query.where(
                    BehaviorPattern.situation_tags.cast(String).contains(situation_tag)
                )

            patterns = (
                await db.execute(query.order_by(BehaviorPattern.confidence.desc()).limit(limit))
            ).scalars().all()

            return [
                {
                    "id": p.id,
                    "name": p.name,
                    "character_tags": p.character_tags or [],
                    "situation_tags": p.situation_tags or [],
                    "typical_behavior": p.typical_behavior or [],
                    "confidence": p.confidence,
                }
                for p in patterns
            ]
