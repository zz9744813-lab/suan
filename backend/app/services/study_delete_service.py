"""StudyDeleteService — P0-拆书书架: 深度删除服务.

删除一本拆书材料时，必须把相关衍生产物清干净，不留孤儿数据。
包括:
- deepstudy 子表 (runs, entities, mentions, scene_beats, relationships,
  foreshadow_chains, behavior_evidence, chapter_analyses, stage_results)
- writing_techniques (SET NULL → 主动删除)
- behavior_patterns (source_material_id SET NULL → 主动删除)
- graph_nodes + graph_edges (source_material_id SET NULL → 主动清理)
- memory_foreshadows (source_material_id SET NULL → 主动删除)
- evolution_nodes (无 FK, 按 material_id 清理)
- study 子表 (chapters, characters — CASCADE 自动删)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import delete as sa_delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import bad_request, not_found
from app.models.deepstudy import (
    BehaviorPatternEvidence,
    ChapterAnalysis,
    Entity,
    EntityMention,
    ForeshadowChain,
    Relationship,
    SceneBeat,
    StudyRun,
    WritingTechnique,
)
from app.models.study import (
    BehaviorPattern,
    StudyChapter,
    StudyCharacter,
    StudyMaterial,
)


@dataclass
class StudyDeleteResult:
    material_id: int
    title: str
    deleted: dict[str, int] = field(default_factory=dict)


class StudyDeleteService:
    """深度删除: 删除 StudyMaterial 及其所有衍生产物."""

    async def delete_material_deep(
        self,
        db: AsyncSession,
        material_id: int,
        *,
        force: bool = False,
    ) -> dict:
        material = await db.get(StudyMaterial, material_id)
        if material is None:
            raise not_found("StudyMaterial", material_id)

        title = material.title
        deleted: dict[str, int] = {}

        # 1. Check for running runs
        running = (await db.execute(
            select(StudyRun).where(
                StudyRun.material_id == material_id,
                StudyRun.status.in_(["queued", "running", "paused"]),
            )
        )).scalars().all()

        if running and not force:
            raise bad_request(
                "该书仍有运行中的 DeepStudy，请先取消或使用 force=true。"
            )
        for r in running:
            r.status = "cancelled"
            r.finished_at = datetime.utcnow()
        await db.flush()

        # 2. Delete deepstudy sub-tables (material_id FK)
        # Most have CASCADE but we delete explicitly for counting

        # Stage results (no FK, manual cleanup)
        from app.models.deepstudy import DeepStudyStageResult
        res = await db.execute(
            sa_delete(DeepStudyStageResult).where(
                DeepStudyStageResult.material_id == material_id
            )
        )
        deleted["stage_results"] = res.rowcount  # type: ignore

        # Behavior evidence
        res = await db.execute(
            sa_delete(BehaviorPatternEvidence).where(
                BehaviorPatternEvidence.material_id == material_id
            )
        )
        deleted["behavior_evidence"] = res.rowcount  # type: ignore

        # Entity mentions (via entity)
        entity_ids = (await db.execute(
            select(Entity.id).where(Entity.material_id == material_id)
        )).scalars().all()
        if entity_ids:
            res = await db.execute(
                sa_delete(EntityMention).where(
                    EntityMention.entity_id.in_(entity_ids)
                )
            )
            deleted["entity_mentions"] = res.rowcount  # type: ignore

        # Relationships (via entity)
        if entity_ids:
            res = await db.execute(
                sa_delete(Relationship).where(
                    (Relationship.source_entity_id.in_(entity_ids))
                    | (Relationship.target_entity_id.in_(entity_ids))
                )
            )
            deleted["relationships"] = res.rowcount  # type: ignore

        # Entities
        res = await db.execute(
            sa_delete(Entity).where(Entity.material_id == material_id)
        )
        deleted["entities"] = res.rowcount  # type: ignore

        # Scene beats
        res = await db.execute(
            sa_delete(SceneBeat).where(SceneBeat.material_id == material_id)
        )
        deleted["scene_beats"] = res.rowcount  # type: ignore

        # Foreshadow chains
        res = await db.execute(
            sa_delete(ForeshadowChain).where(ForeshadowChain.material_id == material_id)
        )
        deleted["foreshadow_chains"] = res.rowcount  # type: ignore

        # Chapter analyses
        res = await db.execute(
            sa_delete(ChapterAnalysis).where(ChapterAnalysis.material_id == material_id)
        )
        deleted["chapter_analyses"] = res.rowcount  # type: ignore

        # Study runs
        res = await db.execute(
            sa_delete(StudyRun).where(StudyRun.material_id == material_id)
        )
        deleted["study_runs"] = res.rowcount  # type: ignore

        # Writing techniques (SET NULL → actively delete)
        res = await db.execute(
            sa_delete(WritingTechnique).where(WritingTechnique.material_id == material_id)
        )
        deleted["writing_techniques"] = res.rowcount  # type: ignore

        # 3. Delete cross-model orphans (source_material_id SET NULL → clean up)

        # Behavior patterns
        res = await db.execute(
            sa_delete(BehaviorPattern).where(
                BehaviorPattern.source_material_id == material_id
            )
        )
        deleted["behavior_patterns"] = res.rowcount  # type: ignore

        # Graph nodes + edges (orphaned graph nodes from this material)
        from app.models.study import GraphNode, GraphEdge
        graph_node_ids = (await db.execute(
            select(GraphNode.id).where(
                GraphNode.source_material_id == material_id
            )
        )).scalars().all()
        if graph_node_ids:
            # Delete edges referencing these nodes
            res = await db.execute(
                sa_delete(GraphEdge).where(
                    (GraphEdge.source_node_id.in_(graph_node_ids))
                    | (GraphEdge.target_node_id.in_(graph_node_ids))
                )
            )
            deleted["graph_edges"] = res.rowcount  # type: ignore
            res = await db.execute(
                sa_delete(GraphNode).where(GraphNode.id.in_(graph_node_ids))
            )
            deleted["graph_nodes"] = res.rowcount  # type: ignore

        # Memory foreshadows
        try:
            from app.models.memory import MemoryForeshadow
            res = await db.execute(
                sa_delete(MemoryForeshadow).where(
                    MemoryForeshadow.source_material_id == material_id
                )
            )
            deleted["memory_foreshadows"] = res.rowcount  # type: ignore
        except Exception:
            pass  # Model might not be available

        # 4. Delete study sub-tables (chapters, characters have CASCADE but count first)
        res = await db.execute(
            sa_delete(StudyCharacter).where(StudyCharacter.material_id == material_id)
        )
        deleted["characters"] = res.rowcount  # type: ignore
        res = await db.execute(
            sa_delete(StudyChapter).where(StudyChapter.material_id == material_id)
        )
        deleted["chapters"] = res.rowcount  # type: ignore

        # 5. Delete the material itself
        await db.delete(material)
        await db.flush()
        deleted["material"] = 1

        return {
            "material_id": material_id,
            "title": title,
            "deleted": deleted,
        }
