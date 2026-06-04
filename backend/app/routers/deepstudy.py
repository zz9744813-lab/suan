"""DeepStudy router (R25 / P0) — book-shelf + per-book knowledge
graph API skeleton.

Scope of P0: this round wires up the data layer and exposes 4
read-mostly endpoints that the library UI (R27) and the per-book
graph UI (R28) will plug into. The actual DeepStudyCoordinatorAgent
+ per-chapter pipelines land in R26.

Endpoints (prefixed ``/api/deepstudy``):

  GET    /library                            book-shelf list + summary
  POST   /materials/{id}/runs                start a DeepStudy run
  GET    /runs/{id}                          run status + progress
  POST   /runs/{id}/pause                    pause a running run
  POST   /runs/{id}/resume                   resume a paused run
  POST   /runs/{id}/cancel                   cancel a running run
  GET    /materials/{id}/knowledge-graph     per-book knowledge graph
  GET    /materials/{id}/nodes/{node_id}     node detail (with evidence)
  GET    /patterns                           behavior pattern library
  GET    /techniques                         writing technique library

R26 will add the actual stage dispatcher + agent invocations.
R25 (this round) only registers the routes, handles empty data
gracefully, and aggregates the existing R22 counters so the UI
can already show non-zero numbers for materials that have been
R22'd (entities, relationships).
"""
from __future__ import annotations

import asyncio
import time as _time
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import String, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
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
    StudyCharacter,
    StudyChapter,
    StudyMaterial,
)
from app.schemas.common import APIResponse
from app.schemas.deepstudy import (
    GraphEdgeRead,
    GraphNodeRead,
    KnowledgeGraphResponse,
    KnowledgeGraphStats,
    LibraryItem,
    LibraryResponse,
    LibrarySummary,
    NodeDetailResponse,
    StudyRunCreate,
    StudyRunRead,
    StudyRunStartResponse,
)

router = APIRouter(prefix="/deepstudy", tags=["deepstudy"])


# ============================================================
# Library — section 6.1
# ============================================================

@router.get("/library", response_model=APIResponse[LibraryResponse])
async def list_library(
    project_id: int | None = Query(default=None, description="按项目过滤 (None=全部)"),
    status: str | None = Query(default=None, description="按 study_status 过滤 (completed/failed/...)"),
    category: str | None = Query(default=None, description="按 shelf_category 过滤"),
    q: str | None = Query(default=None, description="书名/作者模糊搜索"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> APIResponse[LibraryResponse]:
    """List every StudyMaterial as a library row, with deep counters.

    The counters are aggregate queries against the existing
    study_characters / study_behavior_patterns / deepstudy_* tables
    — but we only emit one query per counter to keep this cheap
    even on a 12-book / 2332-chapter library.

    Empty data path: returns ``items: []`` + zeroed summary.
    """
    base = select(StudyMaterial)
    if project_id is not None:
        base = base.where(StudyMaterial.project_id == project_id)
    if status:
        base = base.where(StudyMaterial.study_status == status)
    if category:
        base = base.where(StudyMaterial.shelf_category == category)
    if q:
        base = base.where(
            (StudyMaterial.title.contains(q)) | (StudyMaterial.author.contains(q))
        )
    base = base.order_by(StudyMaterial.updated_at.desc())

    total = (await db.execute(
        select(func.count()).select_from(base.subquery())
    )).scalar_one() or 0

    rows = (await db.execute(
        base.offset((page - 1) * page_size).limit(page_size)
    )).scalars().all()
    if not rows:
        return {
            "ok": True,
            "data": LibraryResponse(
                items=[],
                summary=LibrarySummary(),
                page=page, page_size=page_size, total=total,
            ),
        }

    material_ids = [m.id for m in rows]

    # Counter queries — one per table, scoped to the page's materials.
    # We keep these as subqueries so a single SELECT returns everything.
    entity_counts = dict((await db.execute(
        select(Entity.material_id, func.count(Entity.id))
        .where(Entity.material_id.in_(material_ids))
        .group_by(Entity.material_id)
    )).all() or [])
    scene_beat_counts = dict((await db.execute(
        select(SceneBeat.material_id, func.count(SceneBeat.id))
        .where(SceneBeat.material_id.in_(material_ids))
        .group_by(SceneBeat.material_id)
    )).all() or [])
    rel_counts = dict((await db.execute(
        select(Relationship.material_id, func.count(Relationship.id))
        .where(Relationship.material_id.in_(material_ids))
        .group_by(Relationship.material_id)
    )).all() or [])
    foreshadow_counts = dict((await db.execute(
        select(ForeshadowChain.material_id, func.count(ForeshadowChain.id))
        .where(ForeshadowChain.material_id.in_(material_ids))
        .group_by(ForeshadowChain.material_id)
    )).all() or [])
    behavior_counts = dict((await db.execute(
        select(BehaviorPattern.source_material_id, func.count(BehaviorPattern.id))
        .where(BehaviorPattern.source_material_id.in_(material_ids))
        .group_by(BehaviorPattern.source_material_id)
    )).all() or [])
    technique_counts = dict((await db.execute(
        select(WritingTechnique.material_id, func.count(WritingTechnique.id))
        .where(WritingTechnique.material_id.in_(material_ids))
        .group_by(WritingTechnique.material_id)
    )).all() or [])

    # Run cost is summed across all runs of the material.
    cost_rows = (await db.execute(
        select(StudyRun.material_id, func.coalesce(func.sum(StudyRun.cost_usd), 0.0))
        .where(StudyRun.material_id.in_(material_ids))
        .group_by(StudyRun.material_id)
    )).all() or []
    cost_by_material = {mid: float(c) for mid, c in cost_rows}

    # ``processed_chapters`` comes from the latest run on the material.
    # SQLite-friendly subquery: pick MAX(id) per material.
    latest_run_subq = (
        select(StudyRun.material_id, func.max(StudyRun.id).label("max_id"))
        .where(StudyRun.material_id.in_(material_ids))
        .group_by(StudyRun.material_id)
        .subquery()
    )
    latest_runs = (await db.execute(
        select(StudyRun).join(
            latest_run_subq, StudyRun.id == latest_run_subq.c.max_id
        )
    )).scalars().all()
    latest_by_material = {r.material_id: r for r in latest_runs}

    items: list[LibraryItem] = []
    for m in rows:
        latest = latest_by_material.get(m.id)
        items.append(LibraryItem(
            id=m.id, title=m.title, author=m.author,
            shelf_category=m.shelf_category, cover_theme=m.cover_theme,
            study_status=m.study_status or "empty",
            deepstudy_version=m.deepstudy_version,
            chapter_count=m.chapter_count or 0,
            processed_chapters=(latest.processed_chapters if latest else 0),
            entity_count=entity_counts.get(m.id, 0),
            scene_beat_count=scene_beat_counts.get(m.id, 0),
            relationship_count=rel_counts.get(m.id, 0),
            foreshadow_count=foreshadow_counts.get(m.id, 0),
            behavior_count=behavior_counts.get(m.id, 0),
            technique_count=technique_counts.get(m.id, 0),
            knowledge_score=m.knowledge_score,
            last_deepstudied_at=m.last_deepstudied_at,
            cost_usd=cost_by_material.get(m.id, 0.0),
            project_id=m.project_id,
            created_at=m.created_at, updated_at=m.updated_at,
        ))

    # Summary over ALL materials, not just the page.
    summary = await _build_library_summary(db)
    return {
        "ok": True,
        "data": LibraryResponse(
            items=items, summary=summary,
            page=page, page_size=page_size, total=total,
        ),
    }


async def _build_library_summary(db: AsyncSession) -> LibrarySummary:
    """Compute top-of-shelf totals. One GROUP BY query per counter."""
    status_rows = (await db.execute(
        select(StudyMaterial.study_status, func.count(StudyMaterial.id))
        .group_by(StudyMaterial.study_status)
    )).all() or []
    by_status = {s or "empty": int(c) for s, c in status_rows}

    ent_total = (await db.execute(
        select(func.count(Entity.id))
    )).scalar_one() or 0
    rel_total = (await db.execute(
        select(func.count(Relationship.id))
    )).scalar_one() or 0
    tech_total = (await db.execute(
        select(func.count(WritingTechnique.id))
    )).scalar_one() or 0
    cost_total = (await db.execute(
        select(func.coalesce(func.sum(StudyRun.cost_usd), 0.0))
    )).scalar_one() or 0.0

    return LibrarySummary(
        total_books=sum(by_status.values()),
        completed=by_status.get("completed", 0),
        studying=by_status.get("studying", 0),
        paused=by_status.get("paused", 0),
        review_required=by_status.get("review_required", 0),
        failed=by_status.get("failed", 0),
        empty=by_status.get("empty", 0),
        chapterized=by_status.get("chapterized", 0),
        total_entities=int(ent_total),
        total_relationships=int(rel_total),
        total_techniques=int(tech_total),
        total_cost_usd=float(cost_total),
    )


# ============================================================
# Run lifecycle — sections 6.2 / 6.3 / 6.4
# ============================================================

@router.post(
    "/materials/{material_id}/runs",
    response_model=APIResponse[StudyRunStartResponse],
)
async def start_run(
    material_id: int,
    body: StudyRunCreate = StudyRunCreate(),
    db: AsyncSession = Depends(get_db),
) -> APIResponse[StudyRunStartResponse]:
    """Start a DeepStudy run.

    R25: this is the *synchronous scaffold* — we create the
    ``deepstudy_runs`` row, snapshot the agent plan, and return
    ``run_id`` immediately. R26 wires the actual stage dispatch
    (coordinator + 5 agents) as an asyncio task.

    Until R26 lands, the row stays in ``status='queued'``. The
    caller (UI) will see "queued" in the progress poller and can
    transition it to a real worker later.
    """
    material = await db.get(StudyMaterial, material_id)
    if material is None:
        raise not_found("StudyMaterial", material_id)

    # Count chapters that will be processed (after optional range filter).
    if body.chapter_range and len(body.chapter_range) == 2:
        lo, hi = body.chapter_range
        total = (await db.execute(
            select(func.count(StudyChapter.id))
            .where(
                StudyChapter.material_id == material_id,
                StudyChapter.chapter_index >= lo,
                StudyChapter.chapter_index <= hi,
            )
        )).scalar_one() or 0
    else:
        total = (await db.execute(
            select(func.count(StudyChapter.id))
            .where(StudyChapter.material_id == material_id)
        )).scalar_one() or 0

    agent_plan = {
        "mode": body.mode,
        "chapter_range": body.chapter_range,
        "max_concurrency": body.max_concurrency,
        "model_roles": body.model_roles,
        "stages": _stages_for_mode(body.mode),
    }
    run = StudyRun(
        material_id=material_id,
        project_id=material.project_id,
        status="queued",
        mode=body.mode,
        total_chapters=int(total),
        processed_chapters=0,
        current_stage=None,
        agent_plan=agent_plan,
        progress={stage: 0 for stage in agent_plan["stages"]},
        started_at=datetime.utcnow(),
    )
    db.add(run)
    await db.flush()

    # Best-effort: stamp the material as "studying" so the shelf
    # status colour flips immediately. If R26 fails, the worker
    # will overwrite this.
    material.study_status = "studying"
    material.study_progress = {
        "run_id": run.id,
        "total_chapters": int(total),
        "processed_chapters": 0,
        "current_stage": None,
        "errors": [],
    }
    await db.flush()

    return {
        "ok": True,
        "data": StudyRunStartResponse(
            run_id=run.id,
            material_id=material_id,
            status=run.status,
        ),
    }


def _stages_for_mode(mode: str) -> list[str]:
    """Maps a ``mode`` to the list of stages that should run.

    Full: 8 stages incl. graph + critic. *_only: trims to the
    requested slice so a re-run is cheap.
    """
    if mode == "entities_only":
        return ["chapter_profile", "entity", "scene_beat"]
    if mode == "relationships_only":
        return ["chapter_profile", "relationship"]
    if mode == "behaviors_only":
        return ["chapter_profile", "behavior"]
    if mode == "techniques_only":
        return ["behavior", "technique"]
    if mode == "repair_failed":
        # The actual re-run is decided per-stage by the worker based
        # on which sub-tasks errored; we list all so the UI can show
        # the planned skeleton.
        return [
            "chapter_profile", "entity", "scene_beat", "relationship",
            "foreshadow", "behavior", "technique", "graph", "critic",
        ]
    # "full"
    return [
        "chapter_profile", "entity", "scene_beat", "relationship",
        "foreshadow", "behavior", "technique", "graph", "critic",
    ]


@router.get("/runs/{run_id}", response_model=APIResponse[StudyRunRead])
async def get_run(
    run_id: int,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[StudyRunRead]:
    """Run status + progress snapshot. UI polls this every 2.5s."""
    run = await db.get(StudyRun, run_id)
    if run is None:
        raise not_found("StudyRun", run_id)
    return {
        "ok": True,
        "data": StudyRunRead.model_validate(run),
    }


@router.post("/runs/{run_id}/pause", response_model=APIResponse[StudyRunRead])
async def pause_run(
    run_id: int,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[StudyRunRead]:
    """Mark the run as paused. R26 worker checks this flag between
    sub-tasks. In R25 we just stamp the field.
    """
    run = await db.get(StudyRun, run_id)
    if run is None:
        raise not_found("StudyRun", run_id)
    if run.status in ("succeeded", "failed", "cancelled"):
        raise bad_request(f"run {run_id} 已经处于终态 {run.status}, 不能 pause")
    run.status = "paused"
    material = await db.get(StudyMaterial, run.material_id)
    if material is not None:
        material.study_status = "paused"
    await db.flush()
    return {"ok": True, "data": StudyRunRead.model_validate(run)}


@router.post("/runs/{run_id}/resume", response_model=APIResponse[StudyRunRead])
async def resume_run(
    run_id: int,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[StudyRunRead]:
    """Resume a paused run. R25 stamps the field; R26 worker
    picks it up on the next loop tick.
    """
    run = await db.get(StudyRun, run_id)
    if run is None:
        raise not_found("StudyRun", run_id)
    if run.status != "paused":
        raise bad_request(f"run {run_id} 状态是 {run.status}, 只能 resume 已暂停的 run")
    run.status = "running"
    material = await db.get(StudyMaterial, run.material_id)
    if material is not None:
        material.study_status = "studying"
    await db.flush()
    return {"ok": True, "data": StudyRunRead.model_validate(run)}


@router.post("/runs/{run_id}/cancel", response_model=APIResponse[StudyRunRead])
async def cancel_run(
    run_id: int,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[StudyRunRead]:
    """Mark the run as cancelled. R26 worker stops new sub-tasks.
    """
    run = await db.get(StudyRun, run_id)
    if run is None:
        raise not_found("StudyRun", run_id)
    if run.status in ("succeeded", "failed", "cancelled"):
        raise bad_request(f"run {run_id} 已经是终态 {run.status}")
    run.status = "cancelled"
    run.finished_at = datetime.utcnow()
    material = await db.get(StudyMaterial, run.material_id)
    if material is not None:
        material.study_status = "cancelled"
    await db.flush()
    return {"ok": True, "data": StudyRunRead.model_validate(run)}


# ============================================================
# Knowledge graph — section 6.5
# ============================================================

@router.get(
    "/materials/{material_id}/knowledge-graph",
    response_model=APIResponse[KnowledgeGraphResponse],
)
async def get_knowledge_graph(
    material_id: int,
    view: str = Query(default="all", description="all|chapter|character|relationship|foreshadow|behavior|technique"),
    focus_node_id: str | None = Query(default=None, description="聚焦节点, 1 跳邻居"),
    chapter_index: int | None = Query(default=None, description="只显示该章节点"),
    depth: int = Query(default=1, ge=1, le=3, description="聚焦深度 1-3"),
    min_confidence: float = Query(default=0.0, ge=0.0, le=1.0),
    db: AsyncSession = Depends(get_db),
) -> APIResponse[KnowledgeGraphResponse]:
    """Per-book knowledge graph — the JSON payload the StudyBookGraphPage
    (R28) renders.

    R25: this returns a *minimal* but correct graph — book root +
    entities + relationships. R26 will add scene_beats, foreshadows,
    behavior_patterns, and techniques as additional node types.
    """
    material = await db.get(StudyMaterial, material_id)
    if material is None:
        raise not_found("StudyMaterial", material_id)

    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    by_type: dict[str, int] = {}

    # Book root — always present so the graph is "anchored".
    nodes.append({
        "id": f"book:{material.id}",
        "type": "book",
        "label": material.title or f"#{material.id}",
        "size": 42,
        "score": 1.0,
        "chapter_index": None,
        "extra": {
            "author": material.author,
            "study_status": material.study_status,
            "knowledge_score": material.knowledge_score,
        },
    })
    by_type["book"] = 1

    if view in ("all", "character", "relationship", "foreshadow", "behavior", "technique"):
        # Entities
        ent_rows = (await db.execute(
            select(Entity).where(
                Entity.material_id == material_id,
                Entity.confidence >= min_confidence,
            )
        )).scalars().all()
        for e in ent_rows:
            if chapter_index is not None and e.first_chapter_index is not None \
                    and e.first_chapter_index > chapter_index:
                continue
            nodes.append({
                "id": f"entity:{e.id}",
                "type": e.entity_type or "character",
                "label": e.name,
                "size": max(10, int(20 + 20 * (e.importance or 0.5))),
                "score": e.confidence or 0.5,
                "chapter_index": e.first_chapter_index,
                "extra": {
                    "tags": e.tags or [],
                    "aliases": e.aliases or [],
                    "importance": e.importance,
                },
            })
            by_type[e.entity_type or "character"] = by_type.get(e.entity_type or "character", 0) + 1

    if view in ("all", "relationship"):
        # Relationships
        rel_rows = (await db.execute(
            select(Relationship).where(
                Relationship.material_id == material_id,
                Relationship.confidence >= min_confidence,
            )
        )).scalars().all()
        for r in rel_rows:
            edges.append({
                "id": f"rel:{r.id}",
                "source": f"entity:{r.source_entity_id}",
                "target": f"entity:{r.target_entity_id}",
                "type": r.relation_type or "related",
                "label": r.relation_label or "",
                "weight": r.strength or 0.5,
                "evidence": r.change_summary,
                "extra": {
                    "direction": r.direction,
                    "status": r.status,
                    "evidence_quotes": r.evidence_quotes or [],
                },
            })

    # R26 will add scene_beat / foreshadow / behavior / technique nodes.

    # focus mode: keep only the focused node + its 1-hop neighbours.
    if focus_node_id is not None:
        neighbour_ids: set[str] = {focus_node_id}
        for e in edges:
            if e["source"] == focus_node_id:
                neighbour_ids.add(e["target"])
            elif e["target"] == focus_node_id:
                neighbour_ids.add(e["source"])
        nodes = [n for n in nodes if n["id"] in neighbour_ids or n["id"] == f"book:{material_id}"]
        edges = [
            e for e in edges
            if e["source"] in neighbour_ids and e["target"] in neighbour_ids
        ]

    return {
        "ok": True,
        "data": KnowledgeGraphResponse(
            book={
                "id": material.id,
                "title": material.title,
                "author": material.author,
                "study_status": material.study_status,
            },
            nodes=[GraphNodeRead.model_validate(n) for n in nodes],
            edges=[GraphEdgeRead.model_validate(e) for e in edges],
            stats=KnowledgeGraphStats(
                nodes=len(nodes), edges=len(edges), by_type=by_type,
            ),
        ),
    }


# ============================================================
# Node detail — section 6.6
# ============================================================

@router.get(
    "/materials/{material_id}/nodes/{node_id}",
    response_model=APIResponse[NodeDetailResponse],
)
async def get_node_detail(
    material_id: int,
    node_id: str,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[NodeDetailResponse]:
    """Right-side detail panel for a clicked graph node.

    The ``node_id`` is a stringified composite key like
    ``entity:33`` / ``scene:55`` / ``book:1``. The prefix drives
    the data fetch. Unknown prefixes return an empty payload
    rather than 404 so the UI can render a graceful "no detail
    yet" message while R26 wires up scene/behavior/technique
    sources.
    """
    material = await db.get(StudyMaterial, material_id)
    if material is None:
        raise not_found("StudyMaterial", material_id)

    if node_id == f"book:{material_id}":
        return {
            "ok": True,
            "data": NodeDetailResponse(
                id=node_id, type="book", label=material.title,
                profile={"author": material.author, "study_status": material.study_status},
            ),
        }

    if node_id.startswith("entity:"):
        try:
            eid = int(node_id.split(":", 1)[1])
        except ValueError:
            raise bad_request(f"bad node_id: {node_id}")
        entity = await db.get(Entity, eid)
        if entity is None or entity.material_id != material_id:
            raise not_found("Entity", eid)
        mentions = (await db.execute(
            select(EntityMention).where(EntityMention.entity_id == eid)
            .order_by(EntityMention.id.desc()).limit(50)
        )).scalars().all()
        rels = (await db.execute(
            select(Relationship).where(
                (Relationship.source_entity_id == eid) | (Relationship.target_entity_id == eid)
            )
        )).scalars().all()
        return {
            "ok": True,
            "data": NodeDetailResponse(
                id=node_id, type=entity.entity_type, label=entity.name,
                profile={
                    "role": (entity.profile or {}).get("role"),
                    "tags": entity.tags or [],
                    "aliases": entity.aliases or [],
                    "importance": entity.importance,
                    "confidence": entity.confidence,
                },
                mentions=[
                    {
                        "chapter_id": m.chapter_id,
                        "quote": m.quote,
                        "mention_type": m.mention_type,
                        "context_summary": m.context_summary,
                    }
                    for m in mentions
                ],
                relationships=[
                    {
                        "id": r.id,
                        "type": r.relation_type,
                        "label": r.relation_label,
                        "strength": r.strength,
                        "status": r.status,
                        "change_summary": r.change_summary,
                    }
                    for r in rels
                ],
            ),
        }

    # Other prefixes (scene:, foreshadow:, behavior:, technique:) —
    # not yet wired in R25. Return a stub so the UI doesn't 404.
    return {
        "ok": True,
        "data": NodeDetailResponse(
            id=node_id, type="unknown", label=node_id,
        ),
    }


# ============================================================
# Library views — sections 6.7 / 6.8
# ============================================================

@router.get("/patterns")
async def list_patterns(
    material_id: int | None = Query(default=None),
    character_tag: str | None = Query(default=None),
    situation_tag: str | None = Query(default=None),
    q: str | None = Query(default=None),
    min_confidence: float = Query(default=0.0),
    limit: int = Query(default=50, le=200),
    db: AsyncSession = Depends(get_db),
) -> APIResponse[list[dict[str, Any]]]:
    """Behavior-pattern library — paginated by tags, optional text.

    Returns the existing ``behavior_patterns`` rows (the LLM
    distill target) with their evidence counts.
    """
    base = select(BehaviorPattern)
    if material_id is not None:
        base = base.where(BehaviorPattern.source_material_id == material_id)
    if min_confidence > 0:
        base = base.where(BehaviorPattern.confidence >= min_confidence)
    if character_tag:
        # ``character_tags`` is stored as JSON; the LIKE-based
        # match is good enough for MVP. A proper JSON_CONTAINS
        # would need a MySQL/PG port.
        base = base.where(BehaviorPattern.character_tags.cast(String).contains(character_tag))
    if situation_tag:
        base = base.where(BehaviorPattern.situation_tags.cast(String).contains(situation_tag))
    if q:
        base = base.where(BehaviorPattern.name.contains(q))
    base = base.order_by(BehaviorPattern.confidence.desc()).limit(limit)
    rows = (await db.execute(base)).scalars().all()
    return {"ok": True, "data": [
        {
            "id": r.id,
            "name": r.name,
            "character_tags": r.character_tags or [],
            "situation_tags": r.situation_tags or [],
            "typical_behavior": r.typical_behavior or [],
            "dialogue_style": r.dialogue_style or [],
            "scene_function": r.scene_function or [],
            "risks": r.risks or [],
            "recommended_plot_followup": r.recommended_plot_followup or [],
            "confidence": r.confidence,
            "source_material_id": r.source_material_id,
        }
        for r in rows
    ]}


@router.get("/techniques")
async def list_techniques(
    material_id: int | None = Query(default=None),
    technique_type: str | None = Query(default=None),
    situation: str | None = Query(default=None),
    q: str | None = Query(default=None),
    limit: int = Query(default=50, le=200),
    db: AsyncSession = Depends(get_db),
) -> APIResponse[list[dict[str, Any]]]:
    """Writing-technique library. Empty data path is supported:
    no rows means the technique distiller hasn't run yet.
    """
    base = select(WritingTechnique)
    if material_id is not None:
        base = base.where(WritingTechnique.material_id == material_id)
    if technique_type:
        base = base.where(WritingTechnique.technique_type == technique_type)
    if situation:
        base = base.where(WritingTechnique.applicable_situations.cast(String).contains(situation))
    if q:
        base = base.where(WritingTechnique.name.contains(q))
    base = base.order_by(WritingTechnique.times_used.desc(), WritingTechnique.confidence.desc()).limit(limit)
    rows = (await db.execute(base)).scalars().all()
    return {"ok": True, "data": [
        {
            "id": r.id,
            "name": r.name,
            "technique_type": r.technique_type,
            "summary": r.summary,
            "applicable_situations": r.applicable_situations or [],
            "prompt_hint": r.prompt_hint,
            "anti_pattern": r.anti_pattern,
            "confidence": r.confidence,
            "times_used": r.times_used,
            "source_material_id": r.material_id,
        }
        for r in rows
    ]}
