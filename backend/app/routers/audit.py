"""S5-T2 审计日志 — REST API.

只读端点, 供前端审计面板分页查询。
写入通过 ``audit_service.audit_log()`` 由各 service 内部调用.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.audit_log import AuditLog
from app.schemas.audit import AuditLogListResponse, AuditLogRead

router = APIRouter(prefix="/audit", tags=["audit"])


# ============================================================
# 列表 (支持多维度过滤 + 分页)
# ============================================================
@router.get("/logs", response_model=dict[str, object])
async def list_audit_logs(
    project_id: int | None = None,
    chapter_id: int | None = None,
    event_type: str | None = None,
    actor_type: str | None = None,
    actor_key: str | None = None,
    since_iso: str | None = None,   # "2026-06-01T00:00:00"
    until_iso: str | None = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    """分页查询审计日志.

    Example::

        GET /api/audit/logs?project_id=1&event_type=model_switch&limit=20
        GET /api/audit/logs?actor_type=agent&since_iso=2026-06-01T00:00:00
    """
    stmt = select(AuditLog)

    if project_id is not None:
        stmt = stmt.where(AuditLog.project_id == project_id)
    if chapter_id is not None:
        stmt = stmt.where(AuditLog.chapter_id == chapter_id)
    if event_type is not None:
        stmt = stmt.where(AuditLog.event_type == event_type)
    if actor_type is not None:
        stmt = stmt.where(AuditLog.actor_type == actor_type)
    if actor_key is not None:
        stmt = stmt.where(AuditLog.actor_key == actor_key)
    if since_iso:
        try:
            since_dt = datetime.fromisoformat(since_iso)
            stmt = stmt.where(AuditLog.created_at >= since_dt)
        except ValueError:
            pass
    if until_iso:
        try:
            until_dt = datetime.fromisoformat(until_iso)
            stmt = stmt.where(AuditLog.created_at <= until_dt)
        except ValueError:
            pass

    # total
    total_stmt = stmt.with_only_columns(AuditLog.id)
    total = len((await db.execute(total_stmt)).scalars().all())

    # page
    page_stmt = (
        stmt.order_by(AuditLog.created_at.desc())
        .limit(limit).offset(offset)
    )
    items = (await db.execute(page_stmt)).scalars().all()

    return {
        "ok": True,
        "data": AuditLogListResponse(
            items=[AuditLogRead.model_validate(e) for e in items],
            total=total,
        ).model_dump(),
    }


# ============================================================
# 最近 N 条 (前端面板用)
# ============================================================
@router.get("/logs/recent", response_model=dict[str, object])
async def recent_audit_logs(
    project_id: int | None = None,
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    """最近 N 条审计日志 (前端审计面板用)."""
    stmt = select(AuditLog)
    if project_id is not None:
        stmt = stmt.where(AuditLog.project_id == project_id)
    stmt = (
        stmt.order_by(AuditLog.created_at.desc())
        .limit(limit)
    )
    items = (await db.execute(stmt)).scalars().all()
    return {
        "ok": True,
        "data": [AuditLogRead.model_validate(e).model_dump() for e in items],
    }


# ============================================================
# 按 event_type 统计 (柱状图用)
# ============================================================
@router.get("/stats/by-event", response_model=dict[str, object])
async def audit_stats_by_event(
    project_id: int | None = None,
    days: int = Query(7, ge=1, le=90),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    """按 event_type 分组统计 (最近 N 天)."""
    since = datetime.utcnow() - timedelta(days=days)
    stmt = select(AuditLog).where(AuditLog.created_at >= since)
    if project_id is not None:
        stmt = stmt.where(AuditLog.project_id == project_id)

    rows = (await db.execute(stmt)).scalars().all()
    # 内存分组计数
    counts: dict[str, int] = {}
    for r in rows:
        counts[r.event_type] = counts.get(r.event_type, 0) + 1
    return {
        "ok": True,
        "data": {"days": days, "counts": counts},
    }
