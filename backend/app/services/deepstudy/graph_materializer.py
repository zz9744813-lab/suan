"""GraphMaterializer — auto-generates graph nodes/edges when stages complete.

After a stage completes, the materialiser reads the stage's output
tables (Entity, Relationship, SceneBeat, ForeshadowChain,
BehaviorPatternEvidence, WritingTechnique) and upserts nodes/edges
into the knowledge graph representation.

Node ID conventions (stable composite keys):
  - book:{material_id}
  - chapter:{material_id}:{chapter_index}
  - entity:{entity_id}
  - scene:{scene_beat_id}
  - foreshadow:{foreshadow_chain_id}
  - behavior:{behavior_pattern_evidence_id}
  - technique:{writing_technique_id}

Edge conventions:
  - rel:{relationship_id}     — entity → entity
  - contains:{material_id}:{idx} — chapter contains entity
  - foreshadow_connects:{foreshadow_id} — foreshadow → entities
  - behavior_refs:{evidence_id}  — behavior evidence → entity
  - tech_source:{technique_id}  — technique → source entity
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
    StudyRun,
    WritingTechnique,
)
from app.models.study import StudyChapter


class GraphMaterializer:
    """Reads DeepStudy output tables and produces graph nodes/edges.

    Each stage may produce one or more node/edge types. The
    materialiser is called after each stage and at the end of the
    run for deduplication / merge / importance computation.
    """

    async def materialize_stage_output(
        self, material_id: int, stage_key: str
    ) -> None:
        """After a stage completes, auto-upsert nodes/edges into the graph.

        Currently a scaffold — in production this audits the stage's
        output tables and creates/updates the corresponding graph
        representation.
        """
        async with session_scope() as db:
            if stage_key == "entity_extract":
                await self._materialize_entities(db, material_id)
            elif stage_key == "relationship_analyze":
                await self._materialize_relationships(db, material_id)
            elif stage_key == "scene_beat_extract":
                await self._materialize_scene_beats(db, material_id)
            elif stage_key == "foreshadow_analyze":
                await self._materialize_foreshadows(db, material_id)
            elif stage_key == "behavior_pattern_mine":
                await self._materialize_behavior_evidence(db, material_id)
            elif stage_key == "technique_mine":
                await self._materialize_techniques(db, material_id)

    async def _materialize_entities(self, db, material_id: int) -> None:
        """Create entity nodes for all entities in this material."""
        entities = (
            await db.execute(
                select(Entity).where(Entity.material_id == material_id)
            )
        ).scalars().all()

        for entity in entities:
            # Compute merge_key if not already set
            if not entity.merge_key:
                norm_name = entity.name.strip().lower()
                entity.merge_key = f"{material_id}:{entity.entity_type}:{norm_name}"

        # In production: upsert into graph_nodes with type prefix entity:{id}

    async def _materialize_relationships(self, db, material_id: int) -> None:
        """Create relationship edges between entity nodes."""
        relationships = (
            await db.execute(
                select(Relationship).where(Relationship.material_id == material_id)
            )
        ).scalars().all()

        for rel in relationships:
            # Ensure both entities exist
            source_entity = await db.get(Entity, rel.source_entity_id)
            target_entity = await db.get(Entity, rel.target_entity_id)
            if source_entity is None or target_entity is None:
                continue

            # In production: upsert graph_edge with id rel:{rel.id}

    async def _materialize_scene_beats(self, db, material_id: int) -> None:
        """Create scene beat nodes and link to entity nodes."""
        beats = (
            await db.execute(
                select(SceneBeat).where(SceneBeat.material_id == material_id)
            )
        ).scalars().all()

        for beat in beats:
            # In production:
            # - upsert node scene:{beat.id}
            # - create edges to involved entities from beat.involved_entity_ids
            pass

    async def _materialize_foreshadows(self, db, material_id: int) -> None:
        """Create foreshadow chain nodes."""
        chains = (
            await db.execute(
                select(ForeshadowChain).where(ForeshadowChain.material_id == material_id)
            )
        ).scalars().all()

        for chain in chains:
            # In production:
            # - upsert node foreshadow:{chain.id}
            # - create edges to related entities from chain.related_entity_ids
            pass

    async def _materialize_behavior_evidence(self, db, material_id: int) -> None:
        """Create behavior evidence nodes."""
        evidence_rows = (
            await db.execute(
                select(BehaviorPatternEvidence).where(
                    BehaviorPatternEvidence.material_id == material_id
                )
            )
        ).scalars().all()

        for ev in evidence_rows:
            # In production:
            # - upsert node behavior:{ev.id}
            # - create edge to character entity ev.character_entity_id
            pass

    async def _materialize_techniques(self, db, material_id: int) -> None:
        """Create writing technique nodes."""
        techniques = (
            await db.execute(
                select(WritingTechnique).where(
                    WritingTechnique.material_id == material_id
                )
            )
        ).scalars().all()

        for tech in techniques:
            # In production:
            # - upsert node technique:{tech.id}
            # - create edges to source entities/scenes/behaviours
            pass

    async def finalize_graph(self, material_id: int) -> None:
        """Clean up, merge duplicates, compute importance, generate stats.

        Called after all stages complete.

        Operations:
        - Merge entity nodes with the same merge_key.
        - Compute importance scores from degree / mention count.
        - Generate graph statistics (nodes/edges by type).
        - Update StudyMaterial knowledge_score from the StudyCritic.
        """
        async with session_scope() as db:
            # Compute entity counts per entity_type for stats
            result = await db.execute(
                select(Entity.entity_type, Entity.id)
                .where(Entity.material_id == material_id)
            )
            entities = result.all()

            # Deduplicate by merge_key
            seen_keys: dict[str, int] = {}
            for entity in (
                await db.execute(
                    select(Entity).where(Entity.material_id == material_id)
                )
            ).scalars().all():
                key = entity.merge_key or f"{material_id}:{entity.entity_type}:{entity.name.strip().lower()}"
                if key in seen_keys:
                    # Merge mentions from duplicate into the first entity
                    first_id = seen_keys[key]
                    if first_id != entity.id:
                        mentions = (
                            await db.execute(
                                select(EntityMention).where(
                                    EntityMention.entity_id == entity.id
                                )
                            )
                        ).scalars().all()
                        for mention in mentions:
                            mention.entity_id = first_id
                        # Delete the duplicate entity
                        await db.delete(entity)
                else:
                    seen_keys[key] = entity.id

    async def build_graph_payload(
        self, material_id: int
    ) -> dict[str, list[dict[str, Any]]]:
        """Build the full graph payload (nodes + edges) for the API.

        Returns a dict with 'nodes' and 'edges' lists ready for the
        /api/deepstudy/materials/{id}/knowledge-graph endpoint.
        """
        nodes: list[dict[str, Any]] = []
        edges: list[dict[str, Any]] = []

        async with session_scope() as db:
            # Book root
            from app.models.study import StudyMaterial
            material = await db.get(StudyMaterial, material_id)
            if material is not None:
                nodes.append({
                    "id": f"book:{material_id}",
                    "type": "book",
                    "label": material.title or f"#{material_id}",
                    "size": 42,
                    "score": 1.0,
                    "chapter_index": None,
                    "extra": {"author": material.author},
                })

            # Entities
            entities = (
                await db.execute(
                    select(Entity).where(Entity.material_id == material_id)
                )
            ).scalars().all()
            for e in entities:
                nodes.append({
                    "id": f"entity:{e.id}",
                    "type": e.entity_type or "character",
                    "label": e.name,
                    "size": max(10, int(20 + 20 * (e.importance or 0.5))),
                    "score": e.confidence or 0.5,
                    "chapter_index": e.first_chapter_index,
                    "extra": {"tags": e.tags or [], "aliases": e.aliases or []},
                })

            # Relationships
            rels = (
                await db.execute(
                    select(Relationship).where(Relationship.material_id == material_id)
                )
            ).scalars().all()
            for r in rels:
                edges.append({
                    "id": f"rel:{r.id}",
                    "source": f"entity:{r.source_entity_id}",
                    "target": f"entity:{r.target_entity_id}",
                    "type": r.relation_type or "related",
                    "label": r.relation_label or "",
                    "weight": r.strength or 0.5,
                    "evidence": r.change_summary,
                    "extra": {"direction": r.direction, "status": r.status},
                })

        return {"nodes": nodes, "edges": edges}
