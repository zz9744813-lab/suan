# P0 返工 Phase 3.2 — 拆书书架二层端点
# 放在独立模块避免污染原 study.py 的编码
from __future__ import annotations

import datetime as _dt
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.deepstudy import StudyRun
from app.models.study import (
    BehaviorPattern,
    GraphEdge,
    GraphNode,
    StudyMaterial,
    StudyShelf,
)
from app.schemas import (
    APIResponse,
    StudyBookDashboard,
    StudyMaterialRead,
    StudyShelfCreate,
    StudyShelfRead,
    StudyShelfUpdate,
)


router = APIRouter(prefix="/study", tags=["study-shelves"])


def _not_found(name: str, _id: int) -> Exception:
    from fastapi import HTTPException

    return HTTPException(status_code=404, detail=f"{name}#{_id} not found")


@router.get("/shelves", response_model=APIResponse[list[StudyShelfRead]])
async def list_shelves(
    project_id: int | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> APIResponse[list[StudyShelfRead]]:
    """第一层 — 列出所有书架。

    未分组 (shelf_id IS NULL) 的书会被聚成一个虚拟的 "未分组" 书架。
    """
    q = select(StudyShelf).order_by(StudyShelf.display_order, StudyShelf.id)
    if project_id is not None:
        q = q.where(StudyShelf.project_id == project_id)
    rows = (await db.execute(q)).scalars().all()

    result: list[StudyShelfRead] = []
    for s in rows:
        book_count = (await db.execute(
            select(func.count(StudyMaterial.id))
            .where(StudyMaterial.shelf_id == s.id)
        )).scalar_one()

        # 汇总 tags / genres 前 8
        mat_rows = (await db.execute(
            select(StudyMaterial.genre, StudyMaterial.tags)
            .where(StudyMaterial.shelf_id == s.id)
        )).all()
        genre_counter: dict[str, int] = {}
        tag_counter: dict[str, int] = {}
        for g, ts in mat_rows:
            if g:
                genre_counter[g] = genre_counter.get(g, 0) + 1
            for t in (ts or [])[:8]:
                tag_counter[t] = tag_counter.get(t, 0) + 1
        top_genres = sorted(genre_counter, key=lambda k: -genre_counter[k])[:8]
        top_tags = sorted(tag_counter, key=lambda k: -tag_counter[k])[:8]

        result.append(StudyShelfRead(
            id=s.id,
            project_id=s.project_id,
            name=s.name,
            description=s.description,
            display_order=s.display_order,
            color=s.color,
            book_count=book_count,
            top_genres=top_genres,
            top_tags=top_tags,
            created_at=s.created_at,
            updated_at=s.updated_at,
        ))

    # 虚拟 "未分组" 书架
    ungrouped_count = (await db.execute(
        select(func.count(StudyMaterial.id))
        .where(StudyMaterial.shelf_id.is_(None))
    )).scalar_one()
    if ungrouped_count:
        result.append(StudyShelfRead(
            id=0,
            project_id=project_id,
            name="未分组",
            description="还没放到任何书架的书",
            display_order=9999,
            color="#6b7280",
            book_count=ungrouped_count,
            top_genres=[],
            top_tags=[],
            created_at=_dt.datetime.utcnow(),
            updated_at=_dt.datetime.utcnow(),
        ))

    return {"ok": True, "data": result}


@router.post("/shelves", response_model=APIResponse[StudyShelfRead])
async def create_shelf(
    body: StudyShelfCreate,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[StudyShelfRead]:
    s = StudyShelf(
        name=body.name,
        description=body.description or "",
        project_id=body.project_id,
        display_order=body.display_order,
        color=body.color,
    )
    db.add(s)
    await db.flush()
    return {"ok": True, "data": StudyShelfRead(
        id=s.id, project_id=s.project_id,
        name=s.name, description=s.description,
        display_order=s.display_order, color=s.color,
        book_count=0, top_genres=[], top_tags=[],
        created_at=s.created_at, updated_at=s.updated_at,
    )}


@router.patch("/shelves/{shelf_id}", response_model=APIResponse[StudyShelfRead])
async def update_shelf(
    shelf_id: int,
    body: StudyShelfUpdate,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[StudyShelfRead]:
    s = await db.get(StudyShelf, shelf_id)
    if s is None:
        raise _not_found("StudyShelf", shelf_id)
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(s, k, v)
    await db.flush()
    bc = (await db.execute(
        select(func.count(StudyMaterial.id))
        .where(StudyMaterial.shelf_id == s.id)
    )).scalar_one()
    return {"ok": True, "data": StudyShelfRead(
        id=s.id, project_id=s.project_id,
        name=s.name, description=s.description,
        display_order=s.display_order, color=s.color,
        book_count=bc, top_genres=[], top_tags=[],
        created_at=s.created_at, updated_at=s.updated_at,
    )}


@router.delete("/shelves/{shelf_id}", response_model=APIResponse[dict])
async def delete_shelf(
    shelf_id: int,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[dict]:
    """删除书架 — 书不会被删除，只是 shelf_id 置空（回到未分组）。"""
    s = await db.get(StudyShelf, shelf_id)
    if s is None:
        raise _not_found("StudyShelf", shelf_id)
    await db.execute(
        StudyMaterial.__table__.update()
        .where(StudyMaterial.shelf_id == shelf_id)
        .values(shelf_id=None)
    )
    await db.delete(s)
    await db.flush()
    return {"ok": True, "data": {"deleted": shelf_id}}


@router.get("/books", response_model=APIResponse[list[StudyMaterialRead]])
async def list_books(
    shelf_id: int | None = Query(default=None, description="0=未分组，None=全部"),
    project_id: int | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> APIResponse[list[StudyMaterialRead]]:
    """第二层 — 列出书架上的书。

    shelf_id=0 表示"未分组"虚拟书架。
    """
    q = select(StudyMaterial).order_by(StudyMaterial.updated_at.desc())
    if project_id is not None:
        q = q.where(StudyMaterial.project_id == project_id)
    if shelf_id == 0:
        q = q.where(StudyMaterial.shelf_id.is_(None))
    elif shelf_id is not None:
        q = q.where(StudyMaterial.shelf_id == shelf_id)
    rows = (await db.execute(q)).scalars().all()
    return {"ok": True, "data": [StudyMaterialRead.from_orm_trimmed(r) for r in rows]}


@router.get("/books/{material_id}/dashboard", response_model=APIResponse[StudyBookDashboard])
async def get_book_dashboard(
    material_id: int,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[StudyBookDashboard]:
    """单书仪表盘 — 把书详情页需要的所有数据聚合成一次响应。"""
    material = await db.get(StudyMaterial, material_id)
    if material is None:
        raise _not_found("StudyMaterial", material_id)

    # shelf
    shelf_data: StudyShelfRead | None = None
    if material.shelf_id:
        s = await db.get(StudyShelf, material.shelf_id)
        if s is not None:
            shelf_data = StudyShelfRead(
                id=s.id, project_id=s.project_id,
                name=s.name, description=s.description,
                display_order=s.display_order, color=s.color,
                book_count=0, top_genres=[], top_tags=[],
                created_at=s.created_at, updated_at=s.updated_at,
            )

    # latest DeepStudy run
    latest_run: dict[str, Any] | None = None
    if material.project_id is not None:
        run = (await db.execute(
            select(StudyRun)
            .where(StudyRun.material_id == material_id)
            .order_by(StudyRun.id.desc())
            .limit(1)
        )).scalars().first()
        if run is not None:
            latest_run = {
                "id": run.id,
                "status": run.status,
                "mode": run.mode,
                "total_chapters": run.total_chapters,
                "processed_chapters": run.processed_chapters,
                "current_stage": run.current_stage,
                "started_at": run.started_at.isoformat() if run.started_at else None,
                "completed_at": run.completed_at.isoformat() if run.completed_at else None,
            }

    # 4-stat counts
    n_behaviors = (await db.execute(
        select(func.count(BehaviorPattern.id))
        .where(BehaviorPattern.source_material_id == material_id)
    )).scalar_one()
    n_foreshadows = 0
    try:
        from app.models.memory import MemoryForeshadow
        n_foreshadows = (await db.execute(
            select(func.count(MemoryForeshadow.id))
            .where(MemoryForeshadow.study_material_id == material_id)
        )).scalar_one()
    except Exception:
        pass

    # quality timeline
    timeline: list[dict[str, Any]] = []
    if material.study_quality_score is not None:
        at = material.last_deepstudied_at or material.updated_at
        timeline.append({
            "kind": "composite",
            "score": material.study_quality_score,
            "at": at.isoformat() if at else None,
        })
    if material.knowledge_score is not None and material.knowledge_score != material.study_quality_score:
        timeline.append({
            "kind": "knowledge",
            "score": material.knowledge_score,
            "at": material.updated_at.isoformat() if material.updated_at else None,
        })

    # graph status
    graph_materialized = material.graph_materialized_at is not None
    n_nodes = 0
    n_edges = 0
    if graph_materialized:
        n_nodes = (await db.execute(
            select(func.count(GraphNode.id)).where(GraphNode.ref_study_material_id == material_id)
        )).scalar_one()
        n_edges = (await db.execute(
            select(func.count(GraphEdge.id))
            .where(GraphEdge.project_id == material.project_id)
            .where(GraphEdge.created_at <= material.graph_materialized_at)
        )).scalar_one()

    # project graph size
    project_graph_size: dict[str, int] = {}
    if material.project_id is not None:
        project_graph_size["nodes"] = (await db.execute(
            select(func.count(GraphNode.id)).where(GraphNode.project_id == material.project_id)
        )).scalar_one()
        project_graph_size["edges"] = (await db.execute(
            select(func.count(GraphEdge.id)).where(GraphEdge.project_id == material.project_id)
        )).scalar_one()

    return {"ok": True, "data": StudyBookDashboard(
        material=StudyMaterialRead.from_orm_trimmed(material),
        shelf=shelf_data,
        latest_run=latest_run,
        chapter_count=material.chapter_count,
        character_count=material.character_count,
        behavior_count=n_behaviors,
        foreshadow_count=n_foreshadows,
        quality_timeline=timeline,
        graph_materialized=graph_materialized,
        graph_node_count=n_nodes,
        graph_edge_count=n_edges,
        project_id=material.project_id,
        project_graph_size=project_graph_size,
    )}
