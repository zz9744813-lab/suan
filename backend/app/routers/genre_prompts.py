"""P7: Genre-Prompt mapping routes — drag-drop matrix + traceability."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.errors import bad_request, conflict, not_found
from app.models.genre_prompt_map import GenrePromptMapping, ProjectPromptSnapshot
from app.models.prompt import PromptTemplate
from app.schemas import (
    APIResponse,
    GenrePromptBindRequest,
    GenrePromptMappingRead,
    GenrePromptMatrixResponse,
    GenrePromptReorderRequest,
    GenrePromptUnbindRequest,
    MatrixCell,
    PromptSnapshotDetail,
    PromptSnapshotRead,
    TemplateUsageRead,
)


router = APIRouter(prefix="/genre-prompts", tags=["genre-prompts"])


# ============================================================
# Matrix — full Agent × Genre grid
# ============================================================
@router.get("/matrix", response_model=APIResponse[GenrePromptMatrixResponse])
async def get_matrix(db: AsyncSession = Depends(get_db)):
    # 1. Collect all genres from mappings + templates
    mapping_rows = (await db.execute(
        select(GenrePromptMapping).order_by(
            GenrePromptMapping.agent_role_key, GenrePromptMapping.genre, GenrePromptMapping.sort_order,
        )
    )).scalars().all()

    template_rows = (await db.execute(
        select(PromptTemplate.id, PromptTemplate.template_key, PromptTemplate.name, PromptTemplate.genre)
    )).all()

    tpl_map = {r[0]: {"key": r[1], "name": r[2], "genre": r[3]} for r in template_rows}

    genres = sorted(set(m.genre for m in mapping_rows if m.genre) | set(r[3] for r in template_rows if r[3]))
    agent_keys = sorted(set(m.agent_role_key for m in mapping_rows))

    # If no mappings yet, still show agent roles from prompt templates
    if not agent_keys:
        agent_keys = sorted(set(r[2] for r in template_rows if r[2]))

    # Build cells
    cells: list[MatrixCell] = []
    for m in mapping_rows:
        tpl_info = tpl_map.get(m.prompt_template_id, {})
        cells.append(MatrixCell(
            agent_role_key=m.agent_role_key,
            genre=m.genre,
            prompt_template_id=m.prompt_template_id,
            template_key=tpl_info.get("key"),
            template_name=tpl_info.get("name"),
            priority=m.priority,
            sort_order=m.sort_order,
            state="bound" if m.genre else "fallback",
        ))

    return {"ok": True, "data": GenrePromptMatrixResponse(
        genres=genres, agent_role_keys=agent_keys, cells=cells,
    )}


# ============================================================
# Bind / Unbind
# ============================================================
@router.put("/bind", response_model=APIResponse[GenrePromptMappingRead])
async def bind_prompt(req: GenrePromptBindRequest, db: AsyncSession = Depends(get_db)):
    # Check template exists
    tpl = await db.get(PromptTemplate, req.prompt_template_id)
    if tpl is None:
        raise not_found("PromptTemplate", req.prompt_template_id)

    # Upsert: if same (agent_role_key, genre) exists, update it; else create
    existing = (await db.execute(
        select(GenrePromptMapping).where(
            GenrePromptMapping.agent_role_key == req.agent_role_key,
            GenrePromptMapping.genre == req.genre,
            GenrePromptMapping.prompt_template_id == req.prompt_template_id,
        )
    )).scalar_one_or_none()

    if existing:
        existing.priority = req.priority
        await db.flush()
        return {"ok": True, "data": GenrePromptMappingRead.model_validate(existing)}

    # Count existing for sort_order
    count = (await db.execute(
        select(func.count()).select_from(GenrePromptMapping).where(
            GenrePromptMapping.agent_role_key == req.agent_role_key,
            GenrePromptMapping.genre == req.genre,
        )
    )).scalar() or 0

    mapping = GenrePromptMapping(
        agent_role_key=req.agent_role_key,
        genre=req.genre,
        prompt_template_id=req.prompt_template_id,
        priority=req.priority,
        sort_order=count,
    )
    db.add(mapping)
    await db.flush()
    return {"ok": True, "data": GenrePromptMappingRead.model_validate(mapping)}


@router.delete("/unbind", response_model=APIResponse[dict])
async def unbind_prompt(
    agent_role_key: str, genre: str, prompt_template_id: int,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        delete(GenrePromptMapping).where(
            GenrePromptMapping.agent_role_key == agent_role_key,
            GenrePromptMapping.genre == genre,
            GenrePromptMapping.prompt_template_id == prompt_template_id,
        )
    )
    if result.rowcount == 0:
        raise not_found("GenrePromptMapping", f"{agent_role_key}/{genre}/{prompt_template_id}")
    await db.flush()
    return {"ok": True, "data": {"deleted": result.rowcount}}


# ============================================================
# Reorder (drag-drop sort)
# ============================================================
@router.put("/reorder", response_model=APIResponse[dict])
async def reorder_mappings(req: GenrePromptReorderRequest, db: AsyncSession = Depends(get_db)):
    for item in req.items:
        mapping = await db.get(GenrePromptMapping, item.id)
        if mapping:
            mapping.sort_order = item.sort_order
    await db.flush()
    return {"ok": True, "data": {"updated": len(req.items)}}


# ============================================================
# Available templates for a cell
# ============================================================
@router.get("/available", response_model=APIResponse[list[dict]])
async def available_templates(
    agent_role_key: str, genre: str = "", db: AsyncSession = Depends(get_db)):
    # Templates that match the role, and either match genre or are generic
    rows = (await db.execute(
        select(PromptTemplate).where(
            PromptTemplate.role == agent_role_key,
        ).order_by(PromptTemplate.genre, PromptTemplate.name)
    )).scalars().all()

    # Also include templates with matching genre (even if role doesn't match exactly)
    genre_rows = (await db.execute(
        select(PromptTemplate).where(
            PromptTemplate.genre == genre,
        ).order_by(PromptTemplate.name)
    )).scalars().all()

    seen_ids = set()
    result = []
    for r in list(rows) + list(genre_rows):
        if r.id not in seen_ids:
            seen_ids.add(r.id)
            result.append({
                "id": r.id,
                "template_key": r.template_key,
                "name": r.name,
                "genre": r.genre,
                "category": r.category,
                "role": r.role,
            })
    return {"ok": True, "data": result}


# ============================================================
# Traceability — prompt audit
# ============================================================
@router.get("/projects/{project_id}/prompt-audit", response_model=APIResponse[list[PromptSnapshotDetail]])
async def project_prompt_audit(project_id: int, db: AsyncSession = Depends(get_db)):
    from app.models.project import Chapter

    rows = (await db.execute(
        select(ProjectPromptSnapshot)
        .where(ProjectPromptSnapshot.project_id == project_id)
        .order_by(ProjectPromptSnapshot.created_at.desc())
    )).scalars().all()

    results: list[PromptSnapshotDetail] = []
    for row in rows:
        chapter_title = None
        if row.chapter_id:
            ch = await db.get(Chapter, row.chapter_id)
            if ch:
                chapter_title = ch.title
        results.append(PromptSnapshotDetail(
            id=row.id,
            chapter_id=row.chapter_id,
            chapter_title=chapter_title,
            trigger=row.trigger,
            snapshot_data=row.snapshot_data,
            created_at=row.created_at,
        ))
    return {"ok": True, "data": results}


@router.get("/projects/{project_id}/chapters/{chapter_id}/prompt-audit",
            response_model=APIResponse[PromptSnapshotDetail])
async def chapter_prompt_audit(project_id: int, chapter_id: int, db: AsyncSession = Depends(get_db)):
    from app.models.project import Chapter

    row = (await db.execute(
        select(ProjectPromptSnapshot).where(
            ProjectPromptSnapshot.project_id == project_id,
            ProjectPromptSnapshot.chapter_id == chapter_id,
        ).order_by(ProjectPromptSnapshot.created_at.desc()).limit(1)
    )).scalar_one_or_none()

    if row is None:
        raise not_found("PromptSnapshot", f"project={project_id}/chapter={chapter_id}")

    chapter_title = None
    ch = await db.get(Chapter, chapter_id)
    if ch:
        chapter_title = ch.title

    return {"ok": True, "data": PromptSnapshotDetail(
        id=row.id,
        chapter_id=row.chapter_id,
        chapter_title=chapter_title,
        trigger=row.trigger,
        snapshot_data=row.snapshot_data,
        created_at=row.created_at,
    )}


# ============================================================
# Template usage count
# ============================================================
@router.get("/templates/{template_id}/usage", response_model=APIResponse[TemplateUsageRead])
async def template_usage(template_id: int, db: AsyncSession = Depends(get_db)):
    # Search snapshot_data JSON for references to this template_id
    # SQLite JSON doesn't support deep queries well, so we scan
    rows = (await db.execute(
        select(ProjectPromptSnapshot)
    )).scalars().all()

    chapter_ids: list[int] = []
    for row in rows:
        for _agent_key, info in (row.snapshot_data or {}).items():
            if isinstance(info, dict) and info.get("template_id") == template_id:
                if row.chapter_id and row.chapter_id not in chapter_ids:
                    chapter_ids.append(row.chapter_id)
                break

    return {"ok": True, "data": TemplateUsageRead(
        template_id=template_id,
        total_snapshots=len(chapter_ids),
        chapter_ids=chapter_ids,
    )}
