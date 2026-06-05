"""Behavior Card router — P8 behavior-card-knowledge-base API endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.errors import not_found
from app.models.behavior_card import BehaviorCard, BehaviorCategory
from app.schemas import (
    APIResponse,
    BehaviorCardCreate,
    BehaviorCardDetail,
    BehaviorCardListResponse,
    BehaviorCardMoveRequest,
    BehaviorCardSummary,
    BehaviorCardUpdate,
    BehaviorCategoryCollapseRequest,
    BehaviorCategoryCreate,
    BehaviorCategoryRead,
)
from app.services.behavior_card_service import get_behavior_card_service

router = APIRouter(prefix="/behavior-cards", tags=["behavior-cards"])
cat_router = APIRouter(prefix="/behavior-categories", tags=["behavior-categories"])

svc = get_behavior_card_service()


# ---------------------------------------------------------------------------
# Categories
# ---------------------------------------------------------------------------
@cat_router.get("", response_model=APIResponse[list[BehaviorCategoryRead]])
async def list_categories(db: AsyncSession = Depends(get_db)):
    rows = await svc.list_categories(db)
    out = []
    for r in rows:
        d = BehaviorCategoryRead.model_validate(r)
        d.card_count = getattr(r, "_card_count", 0)  # attached by service
        out.append(d)
    return {"ok": True, "data": out}


@cat_router.patch("/{category_id}/collapse", response_model=APIResponse[BehaviorCategoryRead])
async def toggle_collapse(
    category_id: int, body: BehaviorCategoryCollapseRequest, db: AsyncSession = Depends(get_db)
):
    row = await svc.toggle_collapse(db, category_id, body.is_collapsed)
    if row is None:
        raise not_found("BehaviorCategory", category_id)
    return {"ok": True, "data": BehaviorCategoryRead.model_validate(row)}


# ---------------------------------------------------------------------------
# Cards — list
# ---------------------------------------------------------------------------
@router.get("", response_model=APIResponse[BehaviorCardListResponse])
async def list_cards(
    keyword: str | None = Query(default=None),
    category_id: int | None = Query(default=None),
    role_tags: list[str] | None = Query(default=None),
    scene_tags: list[str] | None = Query(default=None),
    status: str | None = Query(default=None),
    sort: str = Query(default="recent"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    rows, total = await svc.list_cards(
        db,
        keyword=keyword,
        category_id=category_id,
        role_tags=role_tags,
        scene_tags=scene_tags,
        status=status,
        sort=sort,
        page=page,
        page_size=page_size,
    )
    items = [BehaviorCardSummary.model_validate(r) for r in rows]
    return {"ok": True, "data": {"items": items, "total": total}}


# ---------------------------------------------------------------------------
# Cards — detail
# ---------------------------------------------------------------------------
@router.get("/{card_id}", response_model=APIResponse[BehaviorCardDetail])
async def get_card_detail(card_id: int, db: AsyncSession = Depends(get_db)):
    row = await svc.get_card_detail(db, card_id)
    if row is None:
        raise not_found("BehaviorCard", card_id)
    return {"ok": True, "data": BehaviorCardDetail.model_validate(row)}


# ---------------------------------------------------------------------------
# Cards — create
# ---------------------------------------------------------------------------
@router.post("", response_model=APIResponse[BehaviorCardDetail])
async def create_card(body: BehaviorCardCreate, db: AsyncSession = Depends(get_db)):
    row = await svc.create_card(db, body)
    # reload with relationships
    full = await svc.get_card_detail(db, row.id)
    return {"ok": True, "data": BehaviorCardDetail.model_validate(full)}


# ---------------------------------------------------------------------------
# Cards — update
# ---------------------------------------------------------------------------
@router.put("/{card_id}", response_model=APIResponse[BehaviorCardDetail])
async def update_card(
    card_id: int, body: BehaviorCardUpdate, db: AsyncSession = Depends(get_db)
):
    try:
        await svc.update_card(db, card_id, body)
    except ValueError:
        raise not_found("BehaviorCard", card_id)
    full = await svc.get_card_detail(db, card_id)
    return {"ok": True, "data": BehaviorCardDetail.model_validate(full)}


# ---------------------------------------------------------------------------
# Cards — move (drag-drop)
# ---------------------------------------------------------------------------
@router.patch("/{card_id}/move", response_model=APIResponse[BehaviorCardSummary])
async def move_card(
    card_id: int, body: BehaviorCardMoveRequest, db: AsyncSession = Depends(get_db)
):
    try:
        row = await svc.move_card(db, card_id, body.target_category_id, body.sort_order)
    except ValueError:
        raise not_found("BehaviorCard", card_id)
    return {"ok": True, "data": BehaviorCardSummary.model_validate(row)}


# ---------------------------------------------------------------------------
# Cards — archive (soft)
# ---------------------------------------------------------------------------
@router.post("/{card_id}/archive", response_model=APIResponse[dict])
async def archive_card(card_id: int, db: AsyncSession = Depends(get_db)):
    try:
        row = await svc.archive_card(db, card_id)
    except ValueError:
        raise not_found("BehaviorCard", card_id)
    return {"ok": True, "data": {"id": card_id, "status": row.status}}
