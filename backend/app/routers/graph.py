"""Graph routes — Round E (P1-1) 人物关系图谱.

The graph is intentionally simple: two tables
(``graph_nodes`` + ``graph_edges``) and a single ``/api/graph/{project_id}``
endpoint that returns a ``GraphBundle`` (all nodes + all edges) for
one project. The frontend draws the canvas; the backend doesn't try
to compute layout (that's expensive and the UI can do it cheaper
with HTML5 Canvas / SVG).
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.errors import bad_request, not_found
from app.models.study import GraphEdge, GraphNode
from app.schemas import (
    APIResponse,
    GraphBundle,
    GraphEdgeCreate,
    GraphEdgeRead,
    GraphEdgeUpdate,
    GraphNodeCreate,
    GraphNodeRead,
    GraphNodeUpdate,
)


router = APIRouter(prefix="/graph", tags=["graph"])


# -------------------- Nodes --------------------

@router.get("/{project_id}/nodes", response_model=APIResponse[list[GraphNodeRead]])
async def list_nodes(
    project_id: int,
    node_kind: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> APIResponse[list[GraphNodeRead]]:
    stmt = select(GraphNode).where(GraphNode.project_id == project_id)
    if node_kind:
        stmt = stmt.where(GraphNode.node_kind == node_kind)
    rows = (await db.execute(stmt.order_by(GraphNode.name.asc()))).scalars().all()
    return {"ok": True, "data": [GraphNodeRead.model_validate(r) for r in rows]}


@router.post("/{project_id}/nodes", response_model=APIResponse[GraphNodeRead])
async def create_node(
    project_id: int,
    body: GraphNodeCreate,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[GraphNodeRead]:
    row = GraphNode(
        project_id=project_id,
        node_kind=body.node_kind,
        name=body.name,
        source_material_id=body.source_material_id,
        ref_study_character_id=body.ref_study_character_id,
        ref_character_id=body.ref_character_id,
        extra=body.extra,
    )
    db.add(row)
    await db.flush()
    return {"ok": True, "data": GraphNodeRead.model_validate(row)}


@router.patch("/{project_id}/nodes/{node_id}", response_model=APIResponse[GraphNodeRead])
async def update_node(
    project_id: int,
    node_id: int,
    body: GraphNodeUpdate,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[GraphNodeRead]:
    row = await db.get(GraphNode, node_id)
    if row is None or row.project_id != project_id:
        raise not_found("GraphNode", node_id)
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(row, k, v)
    await db.flush()
    return {"ok": True, "data": GraphNodeRead.model_validate(row)}


@router.delete("/{project_id}/nodes/{node_id}", response_model=APIResponse[dict])
async def delete_node(
    project_id: int,
    node_id: int,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[dict]:
    row = await db.get(GraphNode, node_id)
    if row is None or row.project_id != project_id:
        raise not_found("GraphNode", node_id)
    # The FK is ON DELETE CASCADE for edges.source_node_id and
    # edges.target_node_id, so the related edges go with the node.
    await db.delete(row)
    return {"ok": True, "data": {"deleted": node_id}}


# -------------------- Edges --------------------

@router.get("/{project_id}/edges", response_model=APIResponse[list[GraphEdgeRead]])
async def list_edges(
    project_id: int,
    relation: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> APIResponse[list[GraphEdgeRead]]:
    stmt = select(GraphEdge).where(GraphEdge.project_id == project_id)
    if relation:
        stmt = stmt.where(GraphEdge.relation == relation)
    rows = (await db.execute(stmt.order_by(GraphEdge.id.asc()))).scalars().all()
    return {"ok": True, "data": [GraphEdgeRead.model_validate(r) for r in rows]}


@router.post("/{project_id}/edges", response_model=APIResponse[GraphEdgeRead])
async def create_edge(
    project_id: int,
    body: GraphEdgeCreate,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[GraphEdgeRead]:
    # Defensive: source_node_id and target_node_id must reference
    # existing nodes in the same project. The FK enforces the
    # existence check, but we surface a friendlier error if the user
    # mixed projects by accident.
    src = await db.get(GraphNode, body.source_node_id)
    tgt = await db.get(GraphNode, body.target_node_id)
    if src is None or tgt is None:
        raise bad_request("source_node_id 或 target_node_id 不存在。")
    if src.project_id != project_id or tgt.project_id != project_id:
        raise bad_request("Edge 两端必须属于同一个 project。")
    if body.source_node_id == body.target_node_id:
        raise bad_request("Edge 两端不能是同一个节点。")
    row = GraphEdge(
        project_id=project_id,
        source_node_id=body.source_node_id,
        target_node_id=body.target_node_id,
        relation=body.relation,
        weight=body.weight,
        evidence=body.evidence,
        extra=body.extra,
    )
    db.add(row)
    await db.flush()
    return {"ok": True, "data": GraphEdgeRead.model_validate(row)}


@router.patch("/{project_id}/edges/{edge_id}", response_model=APIResponse[GraphEdgeRead])
async def update_edge(
    project_id: int,
    edge_id: int,
    body: GraphEdgeUpdate,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[GraphEdgeRead]:
    row = await db.get(GraphEdge, edge_id)
    if row is None or row.project_id != project_id:
        raise not_found("GraphEdge", edge_id)
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(row, k, v)
    await db.flush()
    return {"ok": True, "data": GraphEdgeRead.model_validate(row)}


@router.delete("/{project_id}/edges/{edge_id}", response_model=APIResponse[dict])
async def delete_edge(
    project_id: int,
    edge_id: int,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[dict]:
    row = await db.get(GraphEdge, edge_id)
    if row is None or row.project_id != project_id:
        raise not_found("GraphEdge", edge_id)
    await db.delete(row)
    return {"ok": True, "data": {"deleted": edge_id}}


# -------------------- Bundle (one-shot fetch for the canvas) --------------------

@router.get("/{project_id}", response_model=APIResponse[GraphBundle])
async def get_graph(
    project_id: int,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[GraphBundle]:
    """Return every node + every edge for one project.

    The frontend prefers a single round-trip so the canvas can lay
    everything out in one go; separate ``/nodes`` + ``/edges`` calls
    would just be two requests returning the same data.
    """
    nodes = (
        await db.execute(
            select(GraphNode)
            .where(GraphNode.project_id == project_id)
            .order_by(GraphNode.name.asc())
        )
    ).scalars().all()
    edges = (
        await db.execute(
            select(GraphEdge)
            .where(GraphEdge.project_id == project_id)
            .order_by(GraphEdge.id.asc())
        )
    ).scalars().all()
    return {
        "ok": True,
        "data": GraphBundle(
            nodes=[GraphNodeRead.model_validate(n) for n in nodes],
            edges=[GraphEdgeRead.model_validate(e) for e in edges],
        ),
    }


# -------------------- Materialise from StudyMaterial --------------------

@router.post(
    "/{project_id}/materialise_from_study/{material_id}",
    response_model=APIResponse[GraphBundle],
)
async def materialise_from_study(
    project_id: int,
    material_id: int,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[GraphBundle]:
    """One-shot helper: read a StudyMaterial's characters and create
    a GraphNode for each (if not already present).

    Designed for the "一键导入拆书人物到图谱" button on the graph
    page. Idempotent: characters whose ``name`` already exists in
    this project's graph are skipped.
    """
    from app.models.study import StudyCharacter, StudyMaterial

    mat = await db.get(StudyMaterial, material_id)
    if mat is None:
        raise not_found("StudyMaterial", material_id)
    chars = (
        await db.execute(
            select(StudyCharacter).where(StudyCharacter.material_id == material_id)
        )
    ).scalars().all()
    existing = (
        await db.execute(
            select(GraphNode).where(GraphNode.project_id == project_id)
        )
    ).scalars().all()
    existing_names = {n.name for n in existing}
    created = 0
    for c in chars:
        if c.name in existing_names:
            continue
        db.add(
            GraphNode(
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
            )
        )
        created += 1
    await db.flush()
    return await get_graph(project_id, db)
