"""Behavior Pattern (行为模式) routes — CRUD + tag-based query.

B1 unified system: the primary data source is ``behavior_cards``.
The legacy ``behavior_patterns`` table is still queried for backward
compatibility (``source=legacy``). Default is ``source=all`` which
reads from both tables and deduplicates by ``source_pattern_id``.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.errors import not_found
from app.models.behavior_card import BehaviorCard, BehaviorCardTag
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


def _card_to_pattern_read(card: BehaviorCard) -> BehaviorPatternRead:
    """Convert a BehaviorCard into a BehaviorPatternRead for the legacy API shape.

    B1 migration helper — tag_type='role' → character_tags,
    tag_type='scene' → situation_tags, fit_score → confidence.
    """
    char_tags: list[str] = []
    sit_tags: list[str] = []
    if card.tags:
        for t in card.tags:
            if t.tag_type == "role":
                char_tags.append(t.tag_name)
            elif t.tag_type == "scene":
                sit_tags.append(t.tag_name)

    behavior_list: list[str] = []
    if card.typical_behavior:
        behavior_list = [
            line.strip() for line in card.typical_behavior.split("\n") if line.strip()
        ]
    elif card.behavior_chain:
        behavior_list = [
            line.strip() for line in card.behavior_chain.split("\n") if line.strip()
        ]

    dialogue_list: list[str] = []
    if card.dialogue_style:
        dialogue_list = [
            line.strip() for line in card.dialogue_style.split("\n") if line.strip()
        ]

    # Collect evidence from BehaviorCardSource (lazy-loaded via relationship)
    evidence_list: list[str] = []
    if hasattr(card, "sources") and card.sources:
        evidence_list = [s.source_excerpt for s in card.sources if s.source_excerpt]

    # Determine source_material_id from the first source entry
    source_mat_id: int | None = None
    if hasattr(card, "sources") and card.sources:
        for s in card.sources:
            if s.book_id is not None:
                source_mat_id = s.book_id
                break

    return BehaviorPatternRead(
        id=card.id,
        source_material_id=source_mat_id,
        name=card.name,
        character_tags=char_tags,
        situation_tags=sit_tags,
        typical_behavior=behavior_list,
        dialogue_style=dialogue_list,
        scene_function=[],
        risks=[],
        recommended_plot_followup=[],
        confidence=card.fit_score or 0.0,
        evidence=evidence_list,
        created_at=card.created_at,
        updated_at=card.updated_at,
    )


async def _query_behavior_cards(
    db: AsyncSession,
    *,
    character: list[str] | None,
    situation: list[str] | None,
    search: str | None,
    source_material_id: int | None,
    limit: int,
) -> list[BehaviorPatternRead]:
    """Query behavior_cards with optional tag-based filtering."""
    stmt = (
        select(BehaviorCard)
        .options(selectinload(BehaviorCard.tags))
        .order_by(BehaviorCard.updated_at.desc())
        .limit(limit)
    )
    cards = (await db.execute(stmt)).scalars().all()

    out: list[BehaviorPatternRead] = []
    for card in cards:
        # Collect tags
        char_tags = [t.tag_name for t in card.tags if t.tag_type == "role"]
        sit_tags = [t.tag_name for t in card.tags if t.tag_type == "scene"]

        # Tag intersect filtering
        if not _intersects(char_tags, character or []):
            continue
        if not _intersects(sit_tags, situation or []):
            continue

        # source_material_id filtering (check via sources relationship)
        if source_material_id is not None:
            matched = False
            if hasattr(card, "sources") and card.sources:
                for s in card.sources:
                    if s.book_id == source_material_id:
                        matched = True
                        break
            if not matched:
                continue

        # Search filtering
        if search:
            needle = search.strip().lower()
            if needle:
                hay = " ".join([
                    card.name or "",
                    card.typical_behavior or "",
                    card.dialogue_style or "",
                    card.summary or "",
                ]).lower()
                if needle not in hay:
                    continue

        out.append(_card_to_pattern_read(card))

    return out


@router.get("/patterns", response_model=APIResponse[list[BehaviorPatternRead]])
async def list_patterns(
    character: list[str] | None = Query(default=None, description="按人物标签过滤(任一命中即可)"),
    situation: list[str] | None = Query(default=None, description="按情境标签过滤(任一命中即可)"),
    search: str | None = Query(default=None, description="在 name/typical_behavior/dialogue_style 里模糊匹配"),
    source_material_id: int | None = Query(default=None),
    source: str = Query(default="all", description="数据源: all(默认) | cards(仅行为卡) | legacy(仅旧表)"),
    limit: int = Query(default=200, le=500),
    db: AsyncSession = Depends(get_db),
) -> APIResponse[list[BehaviorPatternRead]]:
    """B1 unified behavior patterns query.

    Data sources:
      - ``source=all`` (default): queries both ``behavior_cards`` (primary)
        and ``behavior_patterns`` (legacy), deduplicated by ``source_pattern_id``.
      - ``source=cards``: only queries the new ``behavior_cards`` table.
      - ``source=legacy``: only queries the old ``behavior_patterns`` table
        (deprecated — use the migration script to move data).

    Filters:
      - ``character=主角&character=热血``
      - ``situation=公开羞辱``
      - ``search=`` — substring in name / behavior / dialogue text.
    """
    out: list[BehaviorPatternRead] = []
    migrated_ids: set[int] = set()

    # ── 1. Query behavior_cards (B1 primary source) ──────────────────
    if source in ("all", "cards"):
        card_results = await _query_behavior_cards(
            db,
            character=character,
            situation=situation,
            search=search,
            source_material_id=source_material_id,
            limit=limit,
        )
        out.extend(card_results)
        # Track which legacy patterns were already migrated
        for cr in card_results:
            if cr.id:
                # check if this card has a source_pattern_id
                stmt = select(BehaviorCard.source_pattern_id).where(
                    BehaviorCard.id == cr.id
                )
                result = await db.execute(stmt)
                spid = result.scalar_one_or_none()
                if spid is not None:
                    migrated_ids.add(spid)

    # ── 2. Query behavior_patterns (legacy, skip already-migrated) ───
    if source in ("all", "legacy") and len(out) < limit:
        remaining = limit - len(out)
        stmt = select(BehaviorPattern).order_by(BehaviorPattern.updated_at.desc()).limit(remaining)
        if source_material_id is not None:
            stmt = stmt.where(BehaviorPattern.source_material_id == source_material_id)
        rows = (await db.execute(stmt)).scalars().all()
        for r in rows:
            # Skip patterns already migrated to behavior_cards
            if r.id in migrated_ids:
                continue
            if not _intersects(r.character_tags, character or []):
                continue
            if not _intersects(r.situation_tags, situation or []):
                continue
            if search:
                needle = search.strip().lower()
                if needle:
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

