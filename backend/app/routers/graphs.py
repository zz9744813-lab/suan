"""DeepStudy knowledge graph routes — two-layer graph API.

Layer 1 — /graphs/books : list materials with graph summaries
Layer 2 — /graphs/materials/{id} : full network (nodes + edges)
         /graphs/materials/{id}/nodes/{nid} : node detail
         /graphs/materials/{id}/edges/{eid} : edge detail
"""

from __future__ import annotations

from fastapi import APIRouter, Query
from sqlalchemy import select

from app.core.database import session_scope
from app.models.deepstudy_graph import (
    DeepStudyGraph,
    DeepStudyGraphEdge,
    DeepStudyGraphNode,
)
from app.models.study import StudyMaterial

router = APIRouter(prefix="/graphs", tags=["graphs"])


@router.get("/books")
async def list_graph_books(
    status: str | None = Query(None),
    q: str | None = Query(None),
    limit: int = 50,
    offset: int = 0,
):
    """List materials that have a graph summary record (Layer 1)."""
    async with session_scope() as db:
        query = select(DeepStudyGraph)
        if status and status != "all":
            query = query.where(DeepStudyGraph.status == status)
        result = await db.execute(query.limit(limit).offset(offset))
        graphs = result.scalars().all()

        books = []
        for g in graphs:
            mat_result = await db.execute(
                select(StudyMaterial).where(StudyMaterial.id == g.material_id)
            )
            material = mat_result.scalar_one_or_none()
            books.append({
                "material_id": g.material_id,
                "title": material.title if material else f"Material #{g.material_id}",
                "author": material.author if material else None,
                "status": g.status,
                "node_count": g.node_count,
                "edge_count": g.edge_count,
                "character_count": g.character_count,
                "location_count": g.location_count,
                "faction_count": g.faction_count,
                "item_count": g.item_count,
                "event_count": g.event_count,
                "foreshadow_count": g.foreshadow_count,
                "behavior_pattern_count": g.behavior_pattern_count,
                "writing_technique_count": g.writing_technique_count,
                "graph_version": g.graph_version,
                "last_built_at": g.built_at.isoformat() if g.built_at else None,
            })
        return books


@router.get("/materials/{material_id}")
async def get_graph_network(
    material_id: int,
    view: str = "full",
    min_confidence: float = 0.3,
):
    """Full graph network for a material — Layer 2 nodes + edges."""
    async with session_scope() as db:
        graph_result = await db.execute(
            select(DeepStudyGraph).where(DeepStudyGraph.material_id == material_id)
        )
        g = graph_result.scalar_one_or_none()
        if not g:
            return {"graph": None, "nodes": [], "edges": []}

        # Fetch material title separately
        mat_result = await db.execute(
            select(StudyMaterial).where(StudyMaterial.id == material_id)
        )
        mat = mat_result.scalar_one_or_none()
        title = mat.title if mat else f"Material #{material_id}"

        # Nodes
        nodes_query = select(DeepStudyGraphNode).where(
            DeepStudyGraphNode.material_id == material_id
        )
        if min_confidence > 0:
            nodes_query = nodes_query.where(
                DeepStudyGraphNode.confidence >= min_confidence
            )
        nodes_result = await db.execute(nodes_query)
        nodes = nodes_result.scalars().all()

        # Edges
        edges_query = select(DeepStudyGraphEdge).where(
            DeepStudyGraphEdge.material_id == material_id
        )
        if min_confidence > 0:
            edges_query = edges_query.where(
                DeepStudyGraphEdge.confidence >= min_confidence
            )
        edges_result = await db.execute(edges_query)
        edges = edges_result.scalars().all()

        return {
            "graph": {
                "material_id": material_id,
                "title": title,
                "status": g.status,
                "graph_version": g.graph_version,
                "node_count": g.node_count,
                "edge_count": g.edge_count,
                "built_at": g.built_at.isoformat() if g.built_at else None,
            },
            "nodes": [
                {
                    "id": n.id,
                    "node_key": n.node_key,
                    "node_type": n.node_type,
                    "label": n.label,
                    "summary": n.summary,
                    "importance": n.importance,
                    "confidence": n.confidence,
                    "source_stage": n.source_stage,
                    "evidence_json": n.evidence_json,
                    "x": n.x,
                    "y": n.y,
                }
                for n in nodes
            ],
            "edges": [
                {
                    "id": e.id,
                    "edge_key": e.edge_key,
                    "source_node_key": e.source_node_key,
                    "target_node_key": e.target_node_key,
                    "edge_type": e.edge_type,
                    "label": e.label,
                    "summary": e.summary,
                    "weight": e.weight,
                    "confidence": e.confidence,
                    "source_stage": e.source_stage,
                    "evidence_json": e.evidence_json,
                }
                for e in edges
            ],
        }


@router.get("/materials/{material_id}/nodes/{node_id}")
async def get_node_detail(material_id: int, node_id: int):
    """Detail view for a single node, including related edges."""
    async with session_scope() as db:
        node_result = await db.execute(
            select(DeepStudyGraphNode).where(
                DeepStudyGraphNode.id == node_id,
                DeepStudyGraphNode.material_id == material_id,
            )
        )
        n = node_result.scalar_one_or_none()
        if not n:
            return {"detail": None}

        edges_result = await db.execute(
            select(DeepStudyGraphEdge).where(
                (
                    (DeepStudyGraphEdge.source_node_key == n.node_key)
                    | (DeepStudyGraphEdge.target_node_key == n.node_key)
                ),
                DeepStudyGraphEdge.material_id == material_id,
            )
        )
        related = edges_result.scalars().all()

        return {
            "id": n.id,
            "node_key": n.node_key,
            "node_type": n.node_type,
            "label": n.label,
            "summary": n.summary,
            "importance": n.importance,
            "confidence": n.confidence,
            "source_stage": n.source_stage,
            "evidence_json": n.evidence_json,
            "related_edges": [
                {
                    "id": e.id,
                    "edge_type": e.edge_type,
                    "label": e.label,
                    "summary": e.summary,
                }
                for e in related
            ],
        }


@router.get("/materials/{material_id}/edges/{edge_id}")
async def get_edge_detail(material_id: int, edge_id: int):
    """Detail view for a single edge."""
    async with session_scope() as db:
        edge_result = await db.execute(
            select(DeepStudyGraphEdge).where(
                DeepStudyGraphEdge.id == edge_id,
                DeepStudyGraphEdge.material_id == material_id,
            )
        )
        e = edge_result.scalar_one_or_none()
        if not e:
            return {"detail": None}

        return {
            "id": e.id,
            "edge_key": e.edge_key,
            "source_node_key": e.source_node_key,
            "target_node_key": e.target_node_key,
            "edge_type": e.edge_type,
            "label": e.label,
            "summary": e.summary,
            "weight": e.weight,
            "confidence": e.confidence,
            "source_stage": e.source_stage,
            "evidence_json": e.evidence_json,
            "direction": e.direction,
        }
