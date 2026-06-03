"""Memory system routes (MVP slice: characters, foreshadows, hard facts).

Round 9 added the write side (POST/PATCH/DELETE) so the UI can manage the
knowledge graph from /memory. Read endpoints unchanged.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.errors import bad_request, not_found
from app.models.memory import (
    MemoryCharacter,
    MemoryCharacterState,
    MemoryForeshadow,
    MemoryHardFact,
)
from app.models.project import Project
from app.schemas import (
    APIResponse,
    MemoryCharacterCreate,
    MemoryCharacterRead,
    MemoryCharacterStateRead,
    MemoryCharacterUpdate,
    MemoryForeshadowCreate,
    MemoryForeshadowRead,
    MemoryForeshadowUpdate,
    MemoryHardFactCreate,
    MemoryHardFactRead,
)


router = APIRouter(prefix="/memory", tags=["memory"])


# ---- 读 (existing) ----

@router.get("/projects/{project_id}/characters", response_model=APIResponse[list[MemoryCharacterRead]])
async def list_characters(
    project_id: int, db: AsyncSession = Depends(get_db)
) -> APIResponse[list[MemoryCharacterRead]]:
    rows = (await db.execute(
        select(MemoryCharacter)
        .options(selectinload(MemoryCharacter.states))
        .where(MemoryCharacter.project_id == project_id)
        .order_by(MemoryCharacter.id.asc())
    )).scalars().all()
    items: list[MemoryCharacterRead] = []
    for c in rows:
        latest = c.states[0] if c.states else None
        items.append(MemoryCharacterRead(
            id=c.id, project_id=c.project_id, name=c.name, aliases=c.aliases,
            role=c.role, tags=c.tags, base_profile=c.base_profile,
            latest_state=MemoryCharacterStateRead.model_validate(latest) if latest else None,
        ))
    return {"ok": True, "data": items}


@router.get("/projects/{project_id}/foreshadows", response_model=APIResponse[list[MemoryForeshadowRead]])
async def list_foreshadows(
    project_id: int, db: AsyncSession = Depends(get_db)
) -> APIResponse[list[MemoryForeshadowRead]]:
    rows = (await db.execute(
        select(MemoryForeshadow)
        .where(MemoryForeshadow.project_id == project_id)
        .order_by(MemoryForeshadow.importance.desc())
    )).scalars().all()
    return {"ok": True, "data": [MemoryForeshadowRead.model_validate(r) for r in rows]}


@router.get("/projects/{project_id}/hard-facts", response_model=APIResponse[list[MemoryHardFactRead]])
async def list_hard_facts(
    project_id: int, db: AsyncSession = Depends(get_db)
) -> APIResponse[list[MemoryHardFactRead]]:
    rows = (await db.execute(
        select(MemoryHardFact)
        .where(MemoryHardFact.project_id == project_id)
        .order_by(MemoryHardFact.id.desc())
    )).scalars().all()
    return {"ok": True, "data": [MemoryHardFactRead.model_validate(r) for r in rows]}


# ---- 人物 (Characters) ----

async def _ensure_project(db: AsyncSession, project_id: int) -> Project:
    p = await db.get(Project, project_id)
    if p is None:
        raise not_found("Project", project_id)
    return p


@router.post("/projects/{project_id}/characters", response_model=APIResponse[MemoryCharacterRead])
async def create_character(
    project_id: int, body: MemoryCharacterCreate, db: AsyncSession = Depends(get_db)
) -> APIResponse[MemoryCharacterRead]:
    await _ensure_project(db, project_id)
    c = MemoryCharacter(
        project_id=project_id,
        name=body.name,
        aliases=body.aliases,
        role=body.role,
        tags=body.tags,
        base_profile=body.base_profile,
    )
    db.add(c)
    await db.flush()
    await db.refresh(c)
    return {"ok": True, "data": MemoryCharacterRead.model_validate(c)}


@router.patch("/characters/{character_id}", response_model=APIResponse[MemoryCharacterRead])
async def update_character(
    character_id: int, body: MemoryCharacterUpdate, db: AsyncSession = Depends(get_db)
) -> APIResponse[MemoryCharacterRead]:
    c = await db.get(MemoryCharacter, character_id)
    if c is None:
        raise not_found("MemoryCharacter", character_id)
    if body.name is not None: c.name = body.name
    if body.aliases is not None: c.aliases = body.aliases
    if body.role is not None: c.role = body.role
    if body.tags is not None: c.tags = body.tags
    if body.base_profile is not None: c.base_profile = body.base_profile
    await db.flush()
    await db.refresh(c)
    return {"ok": True, "data": MemoryCharacterRead.model_validate(c)}


@router.delete("/characters/{character_id}", response_model=APIResponse[dict])
async def delete_character(
    character_id: int, db: AsyncSession = Depends(get_db)
) -> APIResponse[dict]:
    c = await db.get(MemoryCharacter, character_id)
    if c is None:
        raise not_found("MemoryCharacter", character_id)
    await db.delete(c)
    await db.flush()
    return {"ok": True, "data": {"deleted": character_id}}


# ---- 伏笔 (Foreshadows) ----

@router.post("/projects/{project_id}/foreshadows", response_model=APIResponse[MemoryForeshadowRead])
async def create_foreshadow(
    project_id: int, body: MemoryForeshadowCreate, db: AsyncSession = Depends(get_db)
) -> APIResponse[MemoryForeshadowRead]:
    await _ensure_project(db, project_id)
    f = MemoryForeshadow(
        project_id=project_id, status="active",
        name=body.name, summary=body.summary,
        planted_chapter=body.planted_chapter,
        expected_payoff_chapter=body.expected_payoff_chapter,
        importance=body.importance,
        related_characters=body.related_characters,
        related_items=body.related_items,
        related_main_plot=body.related_main_plot,
    )
    db.add(f)
    await db.flush()
    await db.refresh(f)
    return {"ok": True, "data": MemoryForeshadowRead.model_validate(f)}


@router.patch("/foreshadows/{foreshadow_id}", response_model=APIResponse[MemoryForeshadowRead])
async def update_foreshadow(
    foreshadow_id: int, body: MemoryForeshadowUpdate, db: AsyncSession = Depends(get_db)
) -> APIResponse[MemoryForeshadowRead]:
    f = await db.get(MemoryForeshadow, foreshadow_id)
    if f is None:
        raise not_found("MemoryForeshadow", foreshadow_id)
    if body.status is not None and body.status not in ("active", "paid_off", "dropped"):
        raise bad_request(f"status 必须是 active/paid_off/dropped, 收到: {body.status}")
    for field in (
        "name", "summary", "planted_chapter", "expected_payoff_chapter",
        "actual_payoff_chapter", "status", "importance",
        "related_characters", "related_items", "related_main_plot",
    ):
        val = getattr(body, field)
        if val is not None:
            setattr(f, field, val)
    await db.flush()
    await db.refresh(f)
    return {"ok": True, "data": MemoryForeshadowRead.model_validate(f)}


@router.delete("/foreshadows/{foreshadow_id}", response_model=APIResponse[dict])
async def delete_foreshadow(
    foreshadow_id: int, db: AsyncSession = Depends(get_db)
) -> APIResponse[dict]:
    f = await db.get(MemoryForeshadow, foreshadow_id)
    if f is None:
        raise not_found("MemoryForeshadow", foreshadow_id)
    await db.delete(f)
    await db.flush()
    return {"ok": True, "data": {"deleted": foreshadow_id}}


# ---- 硬事实 (Hard facts) ----

@router.post("/projects/{project_id}/hard-facts", response_model=APIResponse[MemoryHardFactRead])
async def create_hard_fact(
    project_id: int, body: MemoryHardFactCreate, db: AsyncSession = Depends(get_db)
) -> APIResponse[MemoryHardFactRead]:
    await _ensure_project(db, project_id)
    f = MemoryHardFact(
        project_id=project_id, category=body.category, fact=body.fact,
        source_chapter=body.source_chapter,
    )
    db.add(f)
    await db.flush()
    await db.refresh(f)
    return {"ok": True, "data": MemoryHardFactRead.model_validate(f)}


@router.delete("/hard-facts/{fact_id}", response_model=APIResponse[dict])
async def delete_hard_fact(
    fact_id: int, db: AsyncSession = Depends(get_db)
) -> APIResponse[dict]:
    f = await db.get(MemoryHardFact, fact_id)
    if f is None:
        raise not_found("MemoryHardFact", fact_id)
    await db.delete(f)
    await db.flush()
    return {"ok": True, "data": {"deleted": fact_id}}
