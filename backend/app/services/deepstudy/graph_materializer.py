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

from contextlib import asynccontextmanager
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


@asynccontextmanager
async def _db_context(existing_db=None):
    if existing_db is not None:
        yield existing_db
    else:
        async with session_scope() as db:
            yield db


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

    async def finalize_graph(self, material_id: int, db=None) -> None:
        """Clean up, merge duplicates, compute importance, generate stats.

        Called after all stages complete.

        Operations:
        - Merge entity nodes with the same merge_key.
        - Compute importance scores from degree / mention count.
        - Generate graph statistics (nodes/edges by type).
        - Update or create the DeepStudyGraph summary record (Layer 1).
        """
        from datetime import datetime

        from sqlalchemy import func

        from app.models.deepstudy_graph import (
            DeepStudyGraph,
            DeepStudyGraphEdge,
            DeepStudyGraphNode,
        )

        async with _db_context(db) as db:
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

            # ── Layer 1: update/create the DeepStudyGraph summary record ──
            graph_result = await db.execute(
                select(DeepStudyGraph).where(
                    DeepStudyGraph.material_id == material_id
                )
            )
            g = graph_result.scalar_one_or_none()
            if not g:
                g = DeepStudyGraph(material_id=material_id, status="ready")
                db.add(g)

            # Count entities by type
            type_counts = await db.execute(
                select(
                    Entity.entity_type,
                    func.count(Entity.id),
                )
                .where(Entity.material_id == material_id)
                .group_by(Entity.entity_type)
            )
            type_map = {row[0]: row[1] for row in type_counts.all()}

            # Total records from each output table
            rel_count = await db.scalar(
                select(func.count()).select_from(Relationship).where(
                    Relationship.material_id == material_id
                )
            )
            scene_count = await db.scalar(
                select(func.count()).select_from(SceneBeat).where(
                    SceneBeat.material_id == material_id
                )
            )
            foreshadow_count = await db.scalar(
                select(func.count()).select_from(ForeshadowChain).where(
                    ForeshadowChain.material_id == material_id
                )
            )
            behavior_count = await db.scalar(
                select(func.count()).select_from(BehaviorPatternEvidence).where(
                    BehaviorPatternEvidence.material_id == material_id
                )
            )
            technique_count = await db.scalar(
                select(func.count()).select_from(WritingTechnique).where(
                    WritingTechnique.material_id == material_id
                )
            )

            total_entities = sum(type_map.values())
            total_nodes = (
                total_entities
                + (scene_count or 0)
                + (foreshadow_count or 0)
                + (behavior_count or 0)
                + (technique_count or 0)
            )

            g.status = "ready"
            g.node_count = total_nodes
            g.edge_count = rel_count or 0
            g.character_count = type_map.get("character", 0)
            g.location_count = type_map.get("location", 0)
            g.faction_count = type_map.get("faction", 0)
            g.item_count = type_map.get("item", 0)
            g.event_count = type_map.get("event", 0)
            g.foreshadow_count = foreshadow_count or 0
            g.behavior_pattern_count = behavior_count or 0
            g.writing_technique_count = technique_count or 0
            g.built_at = datetime.utcnow()
            g.last_error = None

            await db.flush()

            # P0 返工 Phase 4.2 + 5.5: DeepStudy 完成后自动把书里的图谱节点
            # 物化到 project_id 的 graph_nodes/graph_edges (R22 endpoint
            # 同样的逻辑, 但用 service 内部调, 不走 HTTP)。
            # Phase 5.5 修复 (验收 A5 + 不静默跳过): material 没绑 project_id
            # 时, 必须把原因写到 g.last_error, 不能静默跳过 — 前端图谱诊断
            # 会显示 "material_not_bound_to_project", 用户知道怎么修。
            from app.models.study import StudyMaterial
            material = await db.get(StudyMaterial, material_id)
            if material is not None and material.project_id is not None:
                try:
                    await self._auto_materialise_to_project(
                        db, material.project_id, material_id
                    )
                except Exception as exc:
                    g.last_error = f"auto-materialise failed: {exc!s}"[:400]
                    await db.flush()
            elif material is not None and material.project_id is None:
                g.last_error = (
                    "material_not_bound_to_project: DeepStudy 完成但这本书 "
                    "还没绑到任何 project, 没法物化到 project 图谱。 "
                    "到「拆书」页把书绑到一个项目再重跑。"
                )[:400]
                await db.flush()
            else:
                g.last_error = "material_missing: DeepStudy 完成时找不到对应的 StudyMaterial 行"
                await db.flush()

    async def _auto_materialise_to_project(
        self, db, project_id: int, material_id: int
    ) -> None:
        """P0 返工 Phase 4.2: DeepStudy 完成后, 把这本书的
        人物/伏笔/行为模式自动写入 project 的 graph_nodes,
        并标记 StudyMaterial.graph_materialized_at。
        """
        from datetime import datetime

        from app.models.memory import MemoryForeshadow
        from app.models.study import (
            BehaviorPattern,
            GraphEdge,
            GraphNode,
            StudyCharacter,
        )

        # 只在 material 真有 project 时才物化
        mat_count = (
            await db.execute(
                select(GraphNode.id)
                .where(
                    GraphNode.project_id == project_id,
                    GraphNode.source_material_id == material_id,
                )
                .limit(1)
            )
        ).first()
        if mat_count is not None:
            # 已经物化过 — 跳过 (idempotent)
            return

        from app.models.study import StudyMaterial
        mat = await db.get(StudyMaterial, material_id)
        if mat is None:
            return

        existing_names: set[str] = {
            n.name
            for n in (await db.execute(
                select(GraphNode).where(GraphNode.project_id == project_id)
            )).scalars().all()
        }

        # 1) 人物 (study_character)
        chars = (
            await db.execute(
                select(StudyCharacter).where(StudyCharacter.material_id == material_id)
            )
        ).scalars().all()
        for c in chars:
            if c.name in existing_names:
                continue
            db.add(GraphNode(
                project_id=project_id,
                source_material_id=material_id,
                node_kind="study_character",
                name=c.name,
                ref_study_character_id=c.id,
                extra={
                    "role": c.role,
                    "tags": c.tags or [],
                    "aliases": c.aliases or [],
                },
            ))
            existing_names.add(c.name)

        # 2) 伏笔 (event) — 只在书有 project_id 时才有
        events = (
            await db.execute(
                select(MemoryForeshadow).where(
                    MemoryForeshadow.source_material_id == material_id,
                    MemoryForeshadow.project_id == project_id,
                )
            )
        ).scalars().all()
        for f in events:
            label = f.name
            if label in existing_names:
                continue
            db.add(GraphNode(
                project_id=project_id,
                source_material_id=material_id,
                node_kind="event",
                name=label,
                extra={
                    "summary": (f.summary or "")[:400],
                    "planted_chapter": f.planted_chapter,
                    "importance": f.importance,
                    "status": f.status,
                    "ref_foreshadow_id": f.id,
                },
            ))
            existing_names.add(label)

        # 3) 行为模式 (other)
        patterns = (
            await db.execute(
                select(BehaviorPattern).where(
                    BehaviorPattern.source_material_id == material_id
                )
            )
        ).scalars().all()
        for p in patterns:
            if p.name in existing_names:
                continue
            db.add(GraphNode(
                project_id=project_id,
                source_material_id=material_id,
                node_kind="other",
                name=p.name,
                extra={
                    "kind": "behavior_pattern",
                    "character_tags": p.character_tags or [],
                    "situation_tags": p.situation_tags or [],
                    "ref_behavior_id": p.id,
                },
            ))
            existing_names.add(p.name)

        # 标记物化时间
        mat.graph_materialized_at = datetime.utcnow()
        await db.flush()

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
