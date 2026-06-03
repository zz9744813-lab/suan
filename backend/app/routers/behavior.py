"""Behavior Pattern (行为模式) routes — CRUD + tag-based query."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.errors import not_found
from app.models.study import BehaviorPattern
from app.schemas import (
    APIResponse,
    BehaviorPatternCreate,
    BehaviorPatternRead,
    BehaviorPatternUpdate,
)


router = APIRouter(prefix="/behavior", tags=["behavior"])


def _intersects(a: list[str] | None, b: list[str]) -> bool:
    """Case-insensitive set intersection. Empty list means "no filter"."""
    if not b:
        return True
    if not a:
        return False
    sa = {x.strip().lower() for x in a if x}
    sb = {x.strip().lower() for x in b if x}
    return bool(sa & sb)


@router.get("/patterns", response_model=APIResponse[list[BehaviorPatternRead]])
async def list_patterns(
    character: list[str] | None = Query(default=None, description="按人物标签过滤(任一命中即可)"),
    situation: list[str] | None = Query(default=None, description="按情境标签过滤(任一命中即可)"),
    search: str | None = Query(default=None, description="在 name/typical_behavior/dialogue_style 里模糊匹配"),
    source_material_id: int | None = Query(default=None),
    limit: int = Query(default=200, le=500),
    db: AsyncSession = Depends(get_db),
) -> APIResponse[list[BehaviorPatternRead]]:
    """Round 5 query endpoint.

    Filters:
      - ``character=主角&character=热血`` — match if the pattern's
        character_tags overlap with the requested set (case-insensitive).
      - ``situation=公开羞辱`` — same idea for situation_tags.
      - ``search=`` — substring match against name / typical_behavior /
        dialogue_style.

    The MVP does filter on the application side (load ≤ 200 rows, then
    Python-filter). The dataset is small enough that this is fine, and
    a SQL-only version would need a JSON-tag index that SQLite doesn't
    have. A Postgres migration in production would change this.
    """
    stmt = select(BehaviorPattern).order_by(BehaviorPattern.updated_at.desc()).limit(limit)
    if source_material_id is not None:
        stmt = stmt.where(BehaviorPattern.source_material_id == source_material_id)
    rows = (await db.execute(stmt)).scalars().all()
    out: list[BehaviorPatternRead] = []
    for r in rows:
        if not _intersects(r.character_tags, character or []):
            continue
        if not _intersects(r.situation_tags, situation or []):
            continue
        if search:
            needle = search.strip().lower()
            if not needle:
                pass
            else:
                hay = " ".join([
                    r.name or "",
                    " ".join(r.typical_behavior or []),
                    " ".join(r.dialogue_style or []),
                ]).lower()
                if needle not in hay:
                    continue
        out.append(BehaviorPatternRead.model_validate(r))
    return {"ok": True, "data": out}


@router.post("/patterns", response_model=APIResponse[BehaviorPatternRead])
async def create_pattern(
    body: BehaviorPatternCreate, db: AsyncSession = Depends(get_db)
) -> APIResponse[BehaviorPatternRead]:
    row = BehaviorPattern(**body.model_dump())
    db.add(row)
    await db.flush()
    return {"ok": True, "data": BehaviorPatternRead.model_validate(row)}


@router.get("/patterns/{pattern_id}", response_model=APIResponse[BehaviorPatternRead])
async def get_pattern(
    pattern_id: int, db: AsyncSession = Depends(get_db)
) -> APIResponse[BehaviorPatternRead]:
    row = await db.get(BehaviorPattern, pattern_id)
    if row is None:
        raise not_found("BehaviorPattern", pattern_id)
    return {"ok": True, "data": BehaviorPatternRead.model_validate(row)}


@router.patch("/patterns/{pattern_id}", response_model=APIResponse[BehaviorPatternRead])
async def update_pattern(
    pattern_id: int,
    body: BehaviorPatternUpdate,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[BehaviorPatternRead]:
    row = await db.get(BehaviorPattern, pattern_id)
    if row is None:
        raise not_found("BehaviorPattern", pattern_id)
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(row, k, v)
    await db.flush()
    return {"ok": True, "data": BehaviorPatternRead.model_validate(row)}


@router.delete("/patterns/{pattern_id}", response_model=APIResponse[dict])
async def delete_pattern(
    pattern_id: int, db: AsyncSession = Depends(get_db)
) -> APIResponse[dict]:
    row = await db.get(BehaviorPattern, pattern_id)
    if row is None:
        raise not_found("BehaviorPattern", pattern_id)
    await db.delete(row)
    return {"ok": True, "data": {"deleted": pattern_id}}
