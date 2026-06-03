"""Chapter detail routes (the 创作审计页)."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.errors import not_found
from app.models.project import Chapter, ChapterVersion
from app.models.task import AgentStep
from app.schemas import APIResponse, ChapterRead, ChapterVersionRead


router = APIRouter(prefix="/chapters", tags=["chapters"])


@router.get("/{chapter_id}", response_model=APIResponse[ChapterRead])
async def get_chapter(chapter_id: int, db: AsyncSession = Depends(get_db)) -> APIResponse[ChapterRead]:
    row = await db.get(Chapter, chapter_id)
    if row is None:
        raise not_found("Chapter", chapter_id)
    return {"ok": True, "data": ChapterRead.model_validate(row)}


@router.get("/{chapter_id}/versions", response_model=APIResponse[list[ChapterVersionRead]])
async def list_versions(
    chapter_id: int, db: AsyncSession = Depends(get_db)
) -> APIResponse[list[ChapterVersionRead]]:
    rows = (await db.execute(
        select(ChapterVersion)
        .where(ChapterVersion.chapter_id == chapter_id)
        .order_by(ChapterVersion.id.asc())
    )).scalars().all()
    return {"ok": True, "data": [ChapterVersionRead.model_validate(r) for r in rows]}


@router.get("/{chapter_id}/versions/{kind}", response_model=APIResponse[ChapterVersionRead])
async def get_latest_version(
    chapter_id: int, kind: str, db: AsyncSession = Depends(get_db)
) -> APIResponse[ChapterVersionRead]:
    rows = (await db.execute(
        select(ChapterVersion)
        .where(ChapterVersion.chapter_id == chapter_id, ChapterVersion.version_kind == kind)
        .order_by(ChapterVersion.version_no.desc())
        .limit(1)
    )).scalars().all()
    if not rows:
        raise not_found(f"ChapterVersion({kind})", chapter_id)
    return {"ok": True, "data": ChapterVersionRead.model_validate(rows[0])}


@router.get("/{chapter_id}/steps", response_model=APIResponse[list[dict]])
async def list_steps(chapter_id: int, db: AsyncSession = Depends(get_db)) -> APIResponse[list[dict]]:
    rows = (await db.execute(
        select(AgentStep)
        .where(AgentStep.chapter_id == chapter_id)
        .order_by(AgentStep.id.asc())
    )).scalars().all()
    from app.schemas import AgentStepRead
    return {"ok": True, "data": [AgentStepRead.model_validate(r).model_dump() for r in rows]}
