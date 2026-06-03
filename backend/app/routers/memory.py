"""Memory system routes (MVP slice: characters, foreshadows, hard facts)."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.errors import not_found
from app.models.memory import (
    MemoryCharacter,
    MemoryCharacterState,
    MemoryForeshadow,
    MemoryHardFact,
)
from app.schemas import (
    APIResponse,
    MemoryCharacterRead,
    MemoryCharacterStateRead,
    MemoryForeshadowRead,
    MemoryHardFactRead,
)


router = APIRouter(prefix="/memory", tags=["memory"])


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
