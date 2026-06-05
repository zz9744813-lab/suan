"""P9: Discussion Auto-Trace — Router + Service

10 个 API 端点:
  GET    /api/discussions           — 线程列表
  GET    /api/discussions/stats     — 统计
  POST   /api/discussions           — 手动补充问题
  GET    /api/discussions/{id}      — 详情
  GET    /api/discussions/{id}/messages — 消息列表
  POST   /api/discussions/{id}/run  — 触发执行
  POST   /api/discussions/{id}/solidify-skill — 固化 Skill
  POST   /api/discussions/{id}/extend-recycle  — 延长回收
  POST   /api/discussions/{id}/recycle-now     — 立即回收
  POST   /api/discussions/{id}/restore         — 恢复冷存档
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.errors import not_found
from app.models.discussion_trace import (
    DiscussionIssueSource,
    DiscussionMessage,
    DiscussionRecycleJob,
    DiscussionSkillDraft,
    DiscussionThread,
    Skill,
)
from app.schemas import APIResponse
from app.schemas.discussion_trace import (
    DiscussionStatsResponse,
    ExtendRecycleRequest,
    IssueSourceCreate,
    IssueSourceRead,
    MessageRead,
    SkillDraftRead,
    SkillRead,
    SolidifySkillRequest,
    ThreadCreateRequest,
    ThreadDetail,
    ThreadListResponse,
    ThreadSummary,
)


router = APIRouter(prefix="/discussions", tags=["discussion-trace"])


# ===========================================================================
# Helper: build ThreadSummary from orm + computed fields
# ===========================================================================

async def _build_summary(
    thread: DiscussionThread, db: AsyncSession
) -> ThreadSummary:
    msg_count = (await db.execute(
        select(func.count()).where(DiscussionMessage.thread_id == thread.id)
    )).scalar() or 0

    now = datetime.utcnow()
    remaining = None
    if thread.recycle_at and thread.status not in ("recycled", "ignored"):
        remaining = max(0, (thread.recycle_at - now).total_seconds())

    return ThreadSummary(
        id=thread.id,
        project_id=thread.project_id,
        chapter_id=thread.chapter_id,
        title=thread.title,
        summary=thread.summary,
        source_type=thread.source_type,
        source_agent_role=thread.source_agent_role,
        issue_type=thread.issue_type,
        risk_level=thread.risk_level,
        status=thread.status,
        requires_user_review=thread.requires_user_review,
        final_decision=thread.final_decision,
        recycle_at=thread.recycle_at,
        recycled_at=thread.recycled_at,
        rewrite_task_id=thread.rewrite_task_id,
        skill_draft_id=thread.skill_draft_id,
        issue_fingerprint=thread.issue_fingerprint,
        created_at=thread.created_at,
        updated_at=thread.updated_at,
        message_count=msg_count,
        has_rewrite_task=thread.rewrite_task_id is not None,
        has_skill_draft=thread.skill_draft_id is not None,
        remaining_seconds=remaining,
    )


# ===========================================================================
# API: GET /api/discussions — thread list
# ===========================================================================

@router.get("", response_model=APIResponse[ThreadListResponse])
async def list_threads(
    project_id: int | None = None,
    status: str | None = None,
    issue_type: str | None = None,
    risk_level: str | None = None,
    q: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> APIResponse[ThreadListResponse]:
    stmt = select(DiscussionThread)
    if project_id is not None:
        stmt = stmt.where(DiscussionThread.project_id == project_id)
    if status:
        stmt = stmt.where(DiscussionThread.status == status)
    if issue_type:
        stmt = stmt.where(DiscussionThread.issue_type == issue_type)
    if risk_level:
        stmt = stmt.where(DiscussionThread.risk_level == risk_level)
    if q:
        stmt = stmt.where(DiscussionThread.title.ilike(f"%{q}%"))

    total = (await db.execute(
        select(func.count()).select_from(stmt.subquery())
    )).scalar() or 0

    stmt = stmt.order_by(DiscussionThread.created_at.desc())
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    threads = (await db.execute(stmt)).scalars().all()

    items = []
    for t in threads:
        items.append(await _build_summary(t, db))

    return {"ok": True, "data": ThreadListResponse(items=items, total=total)}


# ===========================================================================
# API: GET /api/discussions/stats
# ===========================================================================

@router.get("/stats", response_model=APIResponse[DiscussionStatsResponse])
async def get_stats(
    project_id: int | None = None,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[DiscussionStatsResponse]:
    base = select(func.count()).select_from(DiscussionThread)
    if project_id is not None:
        base = base.where(DiscussionThread.project_id == project_id)

    active_count = (await db.execute(
        base.where(DiscussionThread.status.in_(["pending_discussion", "discussing"]))
    )).scalar() or 0

    converged_count = (await db.execute(
        base.where(DiscussionThread.status.in_(["converged", "rewrite_created"]))
    )).scalar() or 0

    pending_skill_count = (await db.execute(
        base.where(DiscussionThread.status == "skill_draft_created")
    )).scalar() or 0

    now = datetime.utcnow()
    soon_cutoff = now + timedelta(hours=72)
    recycle_soon_count = (await db.execute(
        base.where(
            DiscussionThread.status.in_(["archived", "skill_draft_created"]),
            DiscussionThread.recycle_at <= soon_cutoff,
            DiscussionThread.recycle_at > now,
        )
    )).scalar() or 0

    total_skill_count = (await db.execute(
        select(func.count()).select_from(Skill)
    )).scalar() or 0

    return {"ok": True, "data": DiscussionStatsResponse(
        active_count=active_count,
        converged_count=converged_count,
        pending_skill_count=pending_skill_count,
        recycle_soon_count=recycle_soon_count,
        total_skill_count=total_skill_count,
    )}


# ===========================================================================
# API: POST /api/discussions — manual supplement
# ===========================================================================

@router.post("", response_model=APIResponse[ThreadSummary])
async def create_thread(
    body: ThreadCreateRequest,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[ThreadSummary]:
    now = datetime.utcnow()
    thread = DiscussionThread(
        project_id=body.project_id,
        chapter_id=body.chapter_id,
        title=body.title,
        source_type="user",
        issue_type=body.issue_type,
        risk_level=body.risk_level,
        status="pending_discussion",
        recycle_at=now + timedelta(days=7),
    )
    db.add(thread)
    await db.flush()

    # add issue source with user note
    if body.user_note:
        db.add(DiscussionIssueSource(
            thread_id=thread.id,
            source_type="user_note",
            problem_summary=body.user_note,
            severity=body.risk_level,
        ))
        await db.flush()

    await db.commit()
    await db.refresh(thread)
    return {"ok": True, "data": await _build_summary(thread, db)}


# ===========================================================================
# API: GET /api/discussions/{thread_id} — detail
# ===========================================================================

@router.get("/{thread_id}", response_model=APIResponse[ThreadDetail])
async def get_thread_detail(
    thread_id: int,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[ThreadDetail]:
    thread = await db.get(DiscussionThread, thread_id)
    if thread is None:
        raise not_found("DiscussionThread", thread_id)

    # issue sources
    sources = (await db.execute(
        select(DiscussionIssueSource)
        .where(DiscussionIssueSource.thread_id == thread_id)
        .order_by(DiscussionIssueSource.created_at.asc())
    )).scalars().all()

    # messages
    messages = (await db.execute(
        select(DiscussionMessage)
        .where(DiscussionMessage.thread_id == thread_id)
        .order_by(DiscussionMessage.created_at.asc())
    )).scalars().all()

    # skill draft
    skill_draft = None
    if thread.skill_draft_id:
        sd = await db.get(DiscussionSkillDraft, thread.skill_draft_id)
        if sd:
            skill_draft = SkillDraftRead.model_validate(sd)

    now = datetime.utcnow()
    remaining = None
    if thread.recycle_at and thread.status not in ("recycled", "ignored"):
        remaining = max(0, (thread.recycle_at - now).total_seconds())

    detail = ThreadDetail(
        id=thread.id,
        project_id=thread.project_id,
        chapter_id=thread.chapter_id,
        task_id=thread.task_id,
        title=thread.title,
        summary=thread.summary,
        source_type=thread.source_type,
        source_agent_role=thread.source_agent_role,
        issue_type=thread.issue_type,
        risk_level=thread.risk_level,
        status=thread.status,
        requires_user_review=thread.requires_user_review,
        final_decision=thread.final_decision,
        final_reason=thread.final_reason,
        final_action_json=thread.final_action_json,
        recycle_at=thread.recycle_at,
        recycled_at=thread.recycled_at,
        archive_payload_json=thread.archive_payload_json,
        rewrite_task_id=thread.rewrite_task_id,
        skill_draft_id=thread.skill_draft_id,
        issue_fingerprint=thread.issue_fingerprint,
        created_at=thread.created_at,
        updated_at=thread.updated_at,
        issue_sources=[IssueSourceRead.model_validate(s) for s in sources],
        messages=[MessageRead.model_validate(m) for m in messages],
        skill_draft=skill_draft,
        message_count=len(messages),
        has_rewrite_task=thread.rewrite_task_id is not None,
        has_skill_draft=thread.skill_draft_id is not None,
        remaining_seconds=remaining,
    )
    return {"ok": True, "data": detail}


# ===========================================================================
# API: GET /api/discussions/{thread_id}/messages
# ===========================================================================

@router.get("/{thread_id}/messages", response_model=APIResponse[list[MessageRead]])
async def get_messages(
    thread_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> APIResponse[list[MessageRead]]:
    thread = await db.get(DiscussionThread, thread_id)
    if thread is None:
        raise not_found("DiscussionThread", thread_id)

    msgs = (await db.execute(
        select(DiscussionMessage)
        .where(DiscussionMessage.thread_id == thread_id)
        .order_by(DiscussionMessage.created_at.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )).scalars().all()

    return {"ok": True, "data": [MessageRead.model_validate(m) for m in msgs]}


# ===========================================================================
# API: POST /api/discussions/{thread_id}/run — trigger execution
# ===========================================================================

@router.post("/{thread_id}/run", response_model=APIResponse[ThreadSummary])
async def run_thread(
    thread_id: int,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[ThreadSummary]:
    thread = await db.get(DiscussionThread, thread_id)
    if thread is None:
        raise not_found("DiscussionThread", thread_id)

    # Only allow running from pending or failed
    if thread.status not in ("pending_discussion", "failed"):
        return {"ok": False, "data": await _build_summary(thread, db),
                "error": f"Cannot run thread in status '{thread.status}'"}

    thread.status = "discussing"
    thread.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(thread)

    # NOTE: The actual orchestrator (P3) will be triggered by the worker.
    # For now, we just move to discussing and the worker picks it up.
    return {"ok": True, "data": await _build_summary(thread, db)}


# ===========================================================================
# API: POST /api/discussions/{thread_id}/solidify-skill
# ===========================================================================

@router.post("/{thread_id}/solidify-skill", response_model=APIResponse[SkillRead])
async def solidify_skill(
    thread_id: int,
    body: SolidifySkillRequest,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[SkillRead]:
    thread = await db.get(DiscussionThread, thread_id)
    if thread is None:
        raise not_found("DiscussionThread", thread_id)

    draft = await db.get(DiscussionSkillDraft, body.draft_id)
    if draft is None or draft.thread_id != thread_id:
        raise not_found("DiscussionSkillDraft", body.draft_id)

    if draft.status == "solidified" and not body.force:
        return {"ok": False, "error": "Already solidified", "data": None}

    # Create formal Skill
    skill = Skill(
        title=draft.title,
        skill_type=draft.skill_type,
        trigger_conditions_json=draft.trigger_conditions_json or [],
        applicable_scenes_json=draft.applicable_scenes_json or [],
        anti_patterns_json=draft.anti_patterns_json or [],
        execution_template=draft.execution_template,
        prompt_snippet=draft.prompt_snippet,
        applicable_agent_roles_json=draft.applicable_agent_roles_json or [],
        source_type="discussion",
        source_thread_id=thread_id,
        quality_score=draft.quality_score,
    )
    db.add(skill)
    await db.flush()

    draft.status = "solidified"
    draft.solidified_at = datetime.utcnow()
    draft.solidified_skill_id = skill.id
    await db.commit()

    await db.refresh(skill)
    return {"ok": True, "data": SkillRead.model_validate(skill)}


# ===========================================================================
# API: POST /api/discussions/{thread_id}/extend-recycle
# ===========================================================================

@router.post("/{thread_id}/extend-recycle", response_model=APIResponse[ThreadSummary])
async def extend_recycle(
    thread_id: int,
    body: ExtendRecycleRequest,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[ThreadSummary]:
    thread = await db.get(DiscussionThread, thread_id)
    if thread is None:
        raise not_found("DiscussionThread", thread_id)

    thread.recycle_at = (thread.recycle_at or datetime.utcnow()) + timedelta(days=body.days)
    thread.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(thread)

    return {"ok": True, "data": await _build_summary(thread, db)}


# ===========================================================================
# API: POST /api/discussions/{thread_id}/recycle-now
# ===========================================================================

@router.post("/{thread_id}/recycle-now", response_model=APIResponse[ThreadSummary])
async def recycle_now(
    thread_id: int,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[ThreadSummary]:
    thread = await db.get(DiscussionThread, thread_id)
    if thread is None:
        raise not_found("DiscussionThread", thread_id)

    if thread.status == "recycled":
        return {"ok": False, "error": "Already recycled", "data": await _build_summary(thread, db)}

    # Compress messages into archive
    messages = (await db.execute(
        select(DiscussionMessage)
        .where(DiscussionMessage.thread_id == thread_id)
        .order_by(DiscussionMessage.created_at.asc())
    )).scalars().all()

    archive = {
        "message_count": len(messages),
        "compressed_messages": [
            {
                "speaker_role": m.speaker_role,
                "content_summary": m.content[:300] if m.content else "",
                "accepted_by_chief": m.accepted_by_chief,
                "confidence": m.confidence,
            }
            for m in messages
        ],
        "recycled_at": datetime.utcnow().isoformat(),
    }
    thread.archive_payload_json = archive
    thread.recycled_at = datetime.utcnow()
    thread.status = "recycled"
    thread.updated_at = datetime.utcnow()

    # Delete raw messages (compressed into archive_payload_json)
    for m in messages:
        await db.delete(m)

    await db.commit()
    await db.refresh(thread)

    return {"ok": True, "data": await _build_summary(thread, db)}


# ===========================================================================
# API: POST /api/discussions/{thread_id}/restore — restore from cold archive
# ===========================================================================

@router.post("/{thread_id}/restore", response_model=APIResponse[ThreadSummary])
async def restore_thread(
    thread_id: int,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[ThreadSummary]:
    thread = await db.get(DiscussionThread, thread_id)
    if thread is None:
        raise not_found("DiscussionThread", thread_id)

    if thread.status != "recycled" or not thread.archive_payload_json:
        return {"ok": False, "error": "Thread is not in recycled state", "data": await _build_summary(thread, db)}

    # Restore messages from archive
    archive = thread.archive_payload_json
    compressed = archive.get("compressed_messages", [])
    for cm in compressed:
        msg = DiscussionMessage(
            thread_id=thread_id,
            speaker_type="agent",
            speaker_role=cm.get("speaker_role", "unknown"),
            content=cm.get("content_summary", ""),
            accepted_by_chief=cm.get("accepted_by_chief", False),
            confidence=cm.get("confidence"),
        )
        db.add(msg)

    thread.status = "archived"
    thread.recycled_at = None
    thread.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(thread)

    return {"ok": True, "data": await _build_summary(thread, db)}
