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
from sqlalchemy import select, insert, func
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.errors import bad_request, not_found
from app.models.study import GraphEdge, GraphNode
from app.schemas import (
    APIResponse,
    GraphBundle,
    GraphDiagnosticsIssue,
    GraphDiagnosticsRead,
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
    # Upsert: on conflict, bump weight and count
    stmt = sqlite_insert(GraphEdge).values(
        project_id=row.project_id,
        source_node_id=row.source_node_id,
        target_node_id=row.target_node_id,
        relation=row.relation,
        weight=row.weight,
        count=1,
        evidence=row.evidence,
        extra=row.extra,
    ).on_conflict_do_update(
        index_elements=["source_node_id", "target_node_id", "relation"],
        set_={
            "weight": GraphEdge.weight + row.weight,
            "count": GraphEdge.count + 1,
            "evidence": row.evidence,
            "extra": row.extra,
            "updated_at": func.now(),
        },
    )
    result = await db.execute(stmt)
    await db.flush()
    # Fetch the resulting row (new or updated)
    row = (await db.execute(
        select(GraphEdge).where(
            GraphEdge.source_node_id == body.source_node_id,
            GraphEdge.target_node_id == body.target_node_id,
            GraphEdge.relation == body.relation,
        )
    )).scalar_one()
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
    # R22: response shape now includes ``materialise_summary`` (a
    # ``{nodes_created, edges_created}`` bag) on top of the standard
    # ``{ok, data, error}`` envelope. Strict ``APIResponse[GraphBundle]``
    # would strip the summary, so we let the dict go out untyped. The
    # frontend already tolerates unknown fields on the envelope.
    response_model=None,
)
async def materialise_from_study(
    project_id: int,
    material_id: int,
    kind: str = Query(
        default="all",
        description=(
            "R22: what to materialise. 'character' = study_characters → "
            "graph nodes (and co-occurrence edges if 'character' or 'all'). "
            "'event' = memory_foreshadows stamped with source_material_id → "
            "graph nodes with node_kind='event'. 'behavior' = behavior_patterns "
            "with source_material_id → graph nodes with node_kind='other' and "
            "tags carried in extra. 'all' (default) = the lot."
        ),
    ),
    add_cooccurrence_edges: bool = Query(
        default=True,
        description=(
            "R22: when materialising characters, also create "
            "graph_edges for each pair that co-occurs in a study chapter. "
            "Edge relation defaults to '同章节出现' which the user can "
            "rename after import."
        ),
    ),
    db: AsyncSession = Depends(get_db),
) -> APIResponse[GraphBundle]:
    """Materialise a StudyMaterial into the project's graph.

    Round 22 (R22) is the "功能联动" round. The original endpoint
    only handled ``study_characters`` → ``graph_nodes``. Now we
    also:

    - materialise the material's foreshadows (rows in
      ``memory_foreshadows`` with ``source_material_id``) as graph
      nodes of kind ``event``, so the graph view shows them next
      to the characters.
    - materialise the material's behavior_patterns as graph nodes
      of kind ``other``, so the user can drag them onto the canvas
      as reference cards. (The writing pipeline already consumes
      them via tag-match; the graph view is just for visualisation.)
    - add co-occurrence edges between characters that share a
      ``source_chapter_id`` so the canvas isn't just a sea of
      unconnected dots.

    Idempotent: characters / events / behaviors whose ``name``
    already exists in this project's graph are skipped. Edges
    are skipped by ``(source, target, relation)`` triple.
    """
    from app.models.memory import MemoryForeshadow
    from app.models.study import (
        BehaviorPattern,
        StudyCharacter,
        StudyMaterial,
    )

    mat = await db.get(StudyMaterial, material_id)
    if mat is None:
        raise not_found("StudyMaterial", material_id)
    if kind not in ("character", "event", "behavior", "all"):
        raise bad_request(
            f"kind 只接受 character|event|behavior|all，收到 {kind!r}。"
        )
    if kind in ("event", "all") and not mat.project_id:
        # Foreshadows live under memory_foreshadows which is
        # project-scoped; a book without project_id has no
        # extracted foreshadows to pull.
        if kind == "event":
            raise bad_request(
                "事件导入需要这本书有 project_id（先把材料绑到 project 跑一次批量抽事件）。",
            )
        # For kind=all we silently skip the event branch.

    want_char = kind in ("character", "all")
    want_event = kind in ("event", "all") and mat.project_id is not None
    want_behavior = kind in ("behavior", "all")

    existing = (
        await db.execute(
            select(GraphNode).where(GraphNode.project_id == project_id)
        )
    ).scalars().all()
    existing_names = {n.name for n in existing}
    # By source-material ref so co-occurrence edges below can find
    # the just-created nodes in O(1) instead of re-querying.
    nodes_by_ref: dict[tuple[str, int], GraphNode] = {}
    for n in existing:
        if n.ref_study_character_id is not None:
            nodes_by_ref[("study_character", n.ref_study_character_id)] = n
        if n.ref_character_id is not None:
            nodes_by_ref[("project_character", n.ref_character_id)] = n
    created = 0

    # --- Characters ---------------------------------------------------
    if want_char:
        chars = (
            await db.execute(
                select(StudyCharacter).where(StudyCharacter.material_id == material_id)
            )
        ).scalars().all()
        for c in chars:
            if c.name in existing_names:
                continue
            node = GraphNode(
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
            db.add(node)
            await db.flush()
            existing_names.add(c.name)
            nodes_by_ref[("study_character", c.id)] = node
            created += 1

    # --- Events (foreshadows) ----------------------------------------
    if want_event:
        events = (
            await db.execute(
                select(MemoryForeshadow).where(
                    MemoryForeshadow.source_material_id == material_id,
                    MemoryForeshadow.project_id == mat.project_id,
                )
            )
        ).scalars().all()
        for f in events:
            label = f.name
            if label in existing_names:
                continue
            node = GraphNode(
                project_id=project_id,
                source_material_id=material_id,
                node_kind="event",
                name=label,
                ref_study_character_id=None,
                extra={
                    "summary": (f.summary or "")[:400],
                    "planted_chapter": f.planted_chapter,
                    "importance": f.importance,
                    "status": f.status,
                    "related_characters": f.related_characters or [],
                    "ref_foreshadow_id": f.id,
                },
            )
            db.add(node)
            await db.flush()
            existing_names.add(label)
            created += 1

    # --- Behavior patterns -------------------------------------------
    if want_behavior:
        patterns = (
            await db.execute(
                select(BehaviorPattern).where(
                    BehaviorPattern.source_material_id == material_id
                )
            )
        ).scalars().all()
        for p in patterns:
            label = p.name
            if label in existing_names:
                continue
            node = GraphNode(
                project_id=project_id,
                source_material_id=material_id,
                node_kind="other",
                name=label,
                ref_study_character_id=None,
                extra={
                    "kind": "behavior_pattern",
                    "character_tags": p.character_tags or [],
                    "situation_tags": p.situation_tags or [],
                    "ref_behavior_id": p.id,
                },
            )
            db.add(node)
            await db.flush()
            existing_names.add(label)
            created += 1

    # --- Co-occurrence edges -----------------------------------------
    edges_created = 0
    if want_char and add_cooccurrence_edges:
        from collections import defaultdict

        # Bucket the material's study_characters by source chapter.
        rows = (
            await db.execute(
                select(StudyCharacter).where(
                    StudyCharacter.material_id == material_id,
                    StudyCharacter.source_chapter_id.is_not(None),
                )
            )
        ).scalars().all()
        chapter_to_chars: dict[int, list[StudyCharacter]] = defaultdict(list)
        for c in rows:
            chapter_to_chars[c.source_chapter_id].append(c)
        # Pairs → count + last chapter.
        pair_acc: dict[tuple[int, int], int] = {}
        for chars_in_chap in chapter_to_chars.values():
            for i, a in enumerate(chars_in_chap[:20]):
                for b in chars_in_chap[i + 1: 20]:
                    lo, hi = (a.id, b.id) if a.id < b.id else (b.id, a.id)
                    pair_acc[(lo, hi)] = pair_acc.get((lo, hi), 0) + 1
        if pair_acc:
            existing_edges = (
                await db.execute(
                    select(GraphEdge).where(GraphEdge.project_id == project_id)
                )
            ).scalars().all()
            edge_key = {
                (e.source_node_id, e.target_node_id, e.relation)
                for e in existing_edges
            }
            for (a_id, b_id), count in pair_acc.items():
                a_node = nodes_by_ref.get(("study_character", a_id))
                b_node = nodes_by_ref.get(("study_character", b_id))
                # If the character wasn't materialised (deduped by
                # name earlier), skip — the user can still add an
                # edge by hand after.
                if a_node is None or b_node is None:
                    continue
                # Don't self-loop.
                if a_node.id == b_node.id:
                    continue
                relation = "同章节出现"
                weight = min(1.0, 0.3 + 0.1 * count)
                if (a_node.id, b_node.id, relation) in edge_key:
                    # Edge exists: bump weight and count via upsert
                    stmt = sqlite_insert(GraphEdge).values(
                        project_id=project_id,
                        source_node_id=a_node.id,
                        target_node_id=b_node.id,
                        relation=relation,
                        weight=weight,
                        count=1,
                    ).on_conflict_do_update(
                        index_elements=["source_node_id", "target_node_id", "relation"],
                        set_={
                            "weight": GraphEdge.weight + weight,
                            "count": GraphEdge.count + 1,
                            "updated_at": func.now(),
                        },
                    )
                    await db.execute(stmt)
                else:
                    db.add(GraphEdge(
                        project_id=project_id,
                        source_node_id=a_node.id,
                        target_node_id=b_node.id,
                        relation=relation,
                        weight=weight,
                        evidence=None,
                    ))
                    edge_key.add((a_node.id, b_node.id, relation))
                    edges_created += 1

    await db.flush()
    # Touch the result so the response carries the full updated
    # graph (matches the original endpoint's contract).
    result = await get_graph(project_id, db)
    # R22: surface the counts we just produced so the UI can show
    # "新增 X 节点 / Y 关系" without parsing the bundle. We add
    # the summary to the same envelope — response_model=None
    # means the dict goes out untyped.
    payload = {
        "ok": True,
        "data": result.get("data") if isinstance(result, dict) else None,
        "error": None,
        "materialise_summary": {
            "nodes_created": created,
            "edges_created": edges_created,
        },
    }
    return payload


# -------------------- P0 返工 Phase 4.3: 图谱诊断 --------------------

@router.get(
    "/{project_id}/diagnostics",
    response_model=APIResponse[GraphDiagnosticsRead],
)
async def graph_diagnostics(
    project_id: int,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[GraphDiagnosticsRead]:
    """图谱诊断 — 告诉前端"图为什么是空的"，并给出修复建议。

    用于 GraphPage 空状态：直接渲染 issues + recommended_actions，
    不用前端自己猜。统计字段（node_count / 边按 relation 拆 /
    贡献过的书）也一次返回，省前端多次 fetch。
    """
    from datetime import datetime as _dt
    from app.models.deepstudy import StudyRun
    from app.models.study import StudyMaterial
    from app.models.project import Project

    # ── 1. 项目是否存在 ───────────────────────────────────────────
    project = await db.get(Project, project_id)
    if project is None:
        raise not_found("Project", project_id)

    # ── 2. 节点/边统计 ────────────────────────────────────────────
    nodes = (
        await db.execute(
            select(GraphNode).where(GraphNode.project_id == project_id)
        )
    ).scalars().all()
    edges = (
        await db.execute(
            select(GraphEdge).where(GraphEdge.project_id == project_id)
        )
    ).scalars().all()

    nodes_by_kind: dict[str, int] = {}
    for n in nodes:
        nodes_by_kind[n.node_kind] = nodes_by_kind.get(n.node_kind, 0) + 1

    edges_by_relation: dict[str, int] = {}
    for e in edges:
        edges_by_relation[e.relation] = edges_by_relation.get(e.relation, 0) + 1
    # top 10 by count
    edges_top = dict(
        sorted(edges_by_relation.items(), key=lambda x: -x[1])[:10]
    )

    last_materialised_at: _dt | None = None
    if nodes:
        last_materialised_at = max(n.updated_at for n in nodes if n.updated_at)

    # ── 3. 贡献过图谱的书 (前置: last_materialise_error 也要用) ──────
    material_ids = sorted({n.source_material_id for n in nodes if n.source_material_id})
    contributing_materials: list[dict[str, Any]] = []
    if material_ids:
        mats = (
            await db.execute(
                select(StudyMaterial).where(StudyMaterial.id.in_(material_ids))
            )
        ).scalars().all()
        # 按 book 给的 node 数排序
        node_count_by_mat: dict[int, int] = {}
        for n in nodes:
            if n.source_material_id:
                node_count_by_mat[n.source_material_id] = node_count_by_mat.get(n.source_material_id, 0) + 1
        for m in mats:
            contributing_materials.append({
                "id": m.id,
                "title": m.title,
                "author": m.author,
                "node_count": node_count_by_mat.get(m.id, 0),
                "study_status": m.study_status,
                "graph_materialized_at": m.graph_materialized_at.isoformat() if m.graph_materialized_at else None,
            })
        contributing_materials.sort(key=lambda x: -x["node_count"])

    # ── P0 返工 Phase 5.5: 拉每本贡献过的书的 DeepStudyGraph.last_error
    # (一个 material 一条, 取第一条非空) — 在 material_ids 之后
    last_materialise_error: str | None = None
    if material_ids:
        from app.models.deepstudy_graph import DeepStudyGraph
        for mid in material_ids:
            ds = (
                await db.execute(
                    select(DeepStudyGraph).where(DeepStudyGraph.material_id == mid)
                )
            ).scalars().first()
            if ds and ds.last_error and not last_materialise_error:
                last_materialise_error = ds.last_error

    # ── 4. Issues + 修复建议 ──────────────────────────────────────
    issues: list[GraphDiagnosticsIssue] = []
    actions: list[dict[str, Any]] = []

    bound_mats = (
        await db.execute(
            select(func.count(StudyMaterial.id)).where(
                StudyMaterial.project_id == project_id
            )
        )
    ).scalar_one() or 0

    if bound_mats == 0:
        issues.append(GraphDiagnosticsIssue(
            severity="error",
            code="no_materials",
            message="这个项目还没绑任何参考书。",
            fix_hint="到「拆书」页加一本参考书，再绑到本项目。",
        ))
        actions.append({
            "code": "go_study",
            "label": "去拆书页加书",
            "target": "/study",
            "priority": 1,
        })
    else:
        # 有书了 — 看有没有 deepstudy run
        runs = (
            await db.execute(
                select(StudyRun)
                .where(StudyRun.project_id == project_id)
                .order_by(StudyRun.id.desc())
                .limit(1)
            )
        ).scalars().first()
        if runs is None:
            issues.append(GraphDiagnosticsIssue(
                severity="warn",
                code="no_deepstudy_run",
                message=f"项目有 {bound_mats} 本书，但还没跑过 DeepStudy。",
                fix_hint="在「拆书」页对其中一本书点「🚀 启动 DeepStudy」。",
            ))
            actions.append({
                "code": "run_deepstudy",
                "label": "去拆书页启动 DeepStudy",
                "target": "/study",
                "priority": 2,
            })
        elif runs.status != "succeeded":
            issues.append(GraphDiagnosticsIssue(
                severity="warn",
                code="deepstudy_in_progress",
                message=f"DeepStudy #{runs.id} 当前状态: {runs.status}。等它跑完。",
            ))
            actions.append({
                "code": "view_run",
                "label": "看 DeepStudy 进度",
                "target": f"/study",
                "priority": 3,
            })

    # 图是空的 — 即使有书 + 有 run, 也要提示怎么物化
    if len(nodes) == 0 and bound_mats > 0:
        issues.append(GraphDiagnosticsIssue(
            severity="info",
            code="not_materialised",
            message="有书但还没贡献到图谱。点下方「一键物化」从书里抽人物/事件/行为模式。",
        ))
        actions.append({
            "code": "materialise",
            "label": "一键物化参考书到图谱",
            "target": f"/graphs/{project_id}/materialise",
            "method": "POST",
            "priority": 1,
        })

    # 节点有但边很稀疏 — 建议开启 R24 enrich
    if len(nodes) > 0 and len(edges) < max(3, len(nodes) // 2):
        issues.append(GraphDiagnosticsIssue(
            severity="info",
            code="sparse_edges",
            message=f"节点 {len(nodes)} 个，但边只有 {len(edges)} 条。可以跑一次关系强化（enrich）。",
        ))

    # 全部都是同一种 kind — 提示可能漏了其他类型
    if len(nodes) > 0 and len(nodes_by_kind) == 1 and "study_character" in nodes_by_kind:
        issues.append(GraphDiagnosticsIssue(
            severity="info",
            code="only_characters",
            message="图谱里只有「拆书人物」。跑 DeepStudy 后会自动加事件/伏笔/行为模式节点。",
        ))

    is_empty = len(nodes) == 0

    diag = GraphDiagnosticsRead(
        project_id=project_id,
        node_count=len(nodes),
        edge_count=len(edges),
        nodes_by_kind=nodes_by_kind,
        edges_by_relation=edges_top,
        contributing_materials=contributing_materials,
        last_materialised_at=last_materialised_at,
        last_materialise_error=last_materialise_error,
        is_empty=is_empty,
        issues=issues,
        recommended_actions=actions,
    )
    return {"ok": True, "data": diag}
