"""Behavior Card service — business logic for P8 behavior-card-knowledge-base."""
from __future__ import annotations

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.behavior_card import (
    BehaviorCard,
    BehaviorCardSource,
    BehaviorCardTag,
    BehaviorCardTechnique,
    BehaviorCardUsageLog,
    BehaviorCategory,
)
from app.schemas.behavior_card import (
    BehaviorCardCreate,
    BehaviorCardUpdate,
    CardTagCreate,
    CardTechniqueCreate,
)


class BehaviorCardService:
    """Stateless service; db session is passed per call."""

    # ------------------------------------------------------------------
    # Categories
    # ------------------------------------------------------------------
    async def list_categories(self, db: AsyncSession) -> list[BehaviorCategory]:
        rows = (
            await db.execute(
                select(BehaviorCategory).order_by(BehaviorCategory.sort_order)
            )
        ).scalars().all()
        # attach card_count
        for cat in rows:
            cnt = (
                await db.execute(
                    select(func.count()).where(BehaviorCard.category_id == cat.id)
                )
            ).scalar() or 0
            cat._card_count = cnt  # type: ignore[attr-defined]
        return rows

    async def get_or_create_category(
        self, db: AsyncSession, slug: str, name: str, **kwargs
    ) -> BehaviorCategory:
        row = (
            await db.execute(
                select(BehaviorCategory).where(BehaviorCategory.slug == slug)
            )
        ).scalar_one_or_none()
        if row:
            return row
        row = BehaviorCategory(slug=slug, name=name, **kwargs)
        db.add(row)
        await db.flush()
        return row

    async def toggle_collapse(
        self, db: AsyncSession, category_id: int, is_collapsed: bool
    ) -> BehaviorCategory:
        row = await db.get(BehaviorCategory, category_id)
        if row is None:
            raise ValueError(f"BehaviorCategory {category_id} not found")
        row.is_collapsed = is_collapsed
        await db.flush()
        return row

    # ------------------------------------------------------------------
    # Cards — list
    # ------------------------------------------------------------------
    async def list_cards(
        self,
        db: AsyncSession,
        *,
        keyword: str | None = None,
        category_id: int | None = None,
        role_tags: list[str] | None = None,
        scene_tags: list[str] | None = None,
        status: str | None = None,
        sort: str = "recent",
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[BehaviorCard], int]:
        stmt = select(BehaviorCard).options(selectinload(BehaviorCard.tags))
        count_stmt = select(func.count()).select_from(BehaviorCard)

        # filters
        if category_id is not None:
            stmt = stmt.where(BehaviorCard.category_id == category_id)
            count_stmt = count_stmt.where(BehaviorCard.category_id == category_id)
        if status:
            stmt = stmt.where(BehaviorCard.status == status)
            count_stmt = count_stmt.where(BehaviorCard.status == status)

        # keyword
        if keyword:
            kw = f"%{keyword}%"
            stmt = stmt.where(
                (BehaviorCard.name.ilike(kw))
                | (BehaviorCard.summary.ilike(kw))
                | (BehaviorCard.behavior_chain.ilike(kw))
                | (BehaviorCard.dialogue_style.ilike(kw))
            )
            count_stmt = count_stmt.where(
                (BehaviorCard.name.ilike(kw))
                | (BehaviorCard.summary.ilike(kw))
            )

        total = (await db.execute(count_stmt)).scalar() or 0

        # sort
        sort_map = {
            "recent": [BehaviorCard.last_used_at.desc().nullslast(), BehaviorCard.updated_at.desc()],
            "fit_score": [BehaviorCard.fit_score.desc()],
            "source_count": [BehaviorCard.source_count.desc()],
            "usage_count": [BehaviorCard.usage_count.desc()],
            "updated_at": [BehaviorCard.updated_at.desc()],
        }
        for col in sort_map.get(sort, sort_map["recent"]):
            stmt = stmt.order_by(col)

        stmt = stmt.offset((page - 1) * page_size).limit(page_size)
        rows = (await db.execute(stmt)).scalars().all()

        # post-filter by tags (application-side for SQLite compatibility)
        if role_tags:
            rt_lower = {t.lower() for t in role_tags}
            rows = [
                r for r in rows
                if any(t.tag_name.lower() in rt_lower for t in r.tags if t.tag_type == "role")
            ]
        if scene_tags:
            st_lower = {t.lower() for t in scene_tags}
            rows = [
                r for r in rows
                if any(t.tag_name.lower() in st_lower for t in r.tags if t.tag_type == "scene")
            ]

        return rows, total

    # ------------------------------------------------------------------
    # Cards — detail
    # ------------------------------------------------------------------
    async def get_card_detail(self, db: AsyncSession, card_id: int) -> BehaviorCard | None:
        stmt = (
            select(BehaviorCard)
            .options(
                selectinload(BehaviorCard.tags),
                selectinload(BehaviorCard.techniques),
                selectinload(BehaviorCard.sources),
                selectinload(BehaviorCard.usage_logs),
                selectinload(BehaviorCard.category),
            )
            .where(BehaviorCard.id == card_id)
        )
        return (await db.execute(stmt)).scalar_one_or_none()

    # ------------------------------------------------------------------
    # Cards — create
    # ------------------------------------------------------------------
    async def create_card(self, db: AsyncSession, payload: BehaviorCardCreate) -> BehaviorCard:
        card = BehaviorCard(
            category_id=payload.category_id,
            name=payload.name,
            role_type=payload.role_type,
            avatar_symbol=payload.avatar_symbol,
            color_theme=payload.color_theme,
            summary=payload.summary,
            typical_behavior=payload.typical_behavior,
            emotion_chain=payload.emotion_chain,
            behavior_chain=payload.behavior_chain,
            dialogue_style=payload.dialogue_style,
            suitable_scenes=payload.suitable_scenes,
            unsuitable_scenes=payload.unsuitable_scenes,
            injection_hint=payload.injection_hint,
            status=payload.status,
        )
        db.add(card)
        await db.flush()

        # tags
        for t in payload.tags:
            db.add(BehaviorCardTag(
                card_id=card.id, tag_type=t.tag_type,
                tag_name=t.tag_name, weight=t.weight,
            ))
        # techniques
        for idx, tech in enumerate(payload.techniques):
            db.add(BehaviorCardTechnique(
                card_id=card.id, title=tech.title, content=tech.content,
                example=tech.example, priority=tech.priority or idx,
            ))

        card.technique_count = len(payload.techniques)
        await db.flush()
        return card

    # ------------------------------------------------------------------
    # Cards — update
    # ------------------------------------------------------------------
    async def update_card(
        self, db: AsyncSession, card_id: int, payload: BehaviorCardUpdate
    ) -> BehaviorCard:
        card = await db.get(BehaviorCard, card_id)
        if card is None:
            raise ValueError(f"BehaviorCard {card_id} not found")

        # scalar fields
        for k, v in payload.model_dump(exclude_unset=True).items():
            if k in ("tags", "techniques"):
                continue
            setattr(card, k, v)

        # replace tags if provided
        if payload.tags is not None:
            await db.execute(
                delete(BehaviorCardTag).where(BehaviorCardTag.card_id == card_id)
            )
            for t in payload.tags:
                db.add(BehaviorCardTag(
                    card_id=card.id, tag_type=t.tag_type,
                    tag_name=t.tag_name, weight=t.weight,
                ))

        # replace techniques if provided
        if payload.techniques is not None:
            await db.execute(
                delete(BehaviorCardTechnique).where(BehaviorCardTechnique.card_id == card_id)
            )
            for idx, tech in enumerate(payload.techniques):
                db.add(BehaviorCardTechnique(
                    card_id=card.id, title=tech.title, content=tech.content,
                    example=tech.example, priority=tech.priority or idx,
                ))
            card.technique_count = len(payload.techniques)

        await db.flush()
        return card

    # ------------------------------------------------------------------
    # Cards — move (drag-drop)
    # ------------------------------------------------------------------
    async def move_card(
        self, db: AsyncSession, card_id: int, target_category_id: int, sort_order: int | None = None
    ) -> BehaviorCard:
        card = await db.get(BehaviorCard, card_id)
        if card is None:
            raise ValueError(f"BehaviorCard {card_id} not found")
        card.category_id = target_category_id
        if sort_order is not None:
            card.sort_order = sort_order
        await db.flush()
        return card

    # ------------------------------------------------------------------
    # Cards — archive (soft)
    # ------------------------------------------------------------------
    async def archive_card(self, db: AsyncSession, card_id: int) -> BehaviorCard:
        card = await db.get(BehaviorCard, card_id)
        if card is None:
            raise ValueError(f"BehaviorCard {card_id} not found")
        card.status = "archived"
        await db.flush()
        return card

    # ------------------------------------------------------------------
    # Usage logging
    # ------------------------------------------------------------------
    async def log_usage(
        self,
        db: AsyncSession,
        card_id: int,
        *,
        project_id: int | None = None,
        chapter_id: int | None = None,
        task_id: int | None = None,
        agent_role: str | None = None,
        usage_type: str | None = None,
        prompt_excerpt: str | None = None,
        output_excerpt: str | None = None,
        feedback_score: float | None = None,
    ) -> None:
        from datetime import datetime, timezone
        card = await db.get(BehaviorCard, card_id)
        if card is None:
            return
        db.add(BehaviorCardUsageLog(
            card_id=card_id,
            project_id=project_id,
            chapter_id=chapter_id,
            task_id=task_id,
            agent_role=agent_role,
            usage_type=usage_type,
            prompt_excerpt=prompt_excerpt,
            output_excerpt=output_excerpt,
            feedback_score=feedback_score,
        ))
        card.usage_count = (card.usage_count or 0) + 1
        card.last_used_at = datetime.now(timezone.utc)
        await db.flush()


# module-level singleton
_svc: BehaviorCardService | None = None


def get_behavior_card_service() -> BehaviorCardService:
    global _svc
    if _svc is None:
        _svc = BehaviorCardService()
    return _svc
