"""P6 §6: 评论/评论组/读者评审 — REST API (P1 阶段).

P1 范围:
  - 17 端点, 全部直接读写 DB
  - 不调 LLM (P2/P3 才补)
  - 不做自动 triage 触发 (§5 worker, P4)
  - discuss / cleanup / run 这些"动作"端点是状态转换, 在 P1
    只写状态 + 占位, 实际执行 (建 DiscussionSession / 跑 reader)
    推到 P2/P3

P1 不做的事:
  - 不入队 (worker 还没扩展到 event-driven, P4)
  - 不调 LLM
  - 不发 SSE 事件 (event_bus 留给 P2 reader 完成时)
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.errors import bad_request, not_found
from app.models.comment_review import (
    ReaderAgentProfile,
    ReaderReviewRun,
    ReviewComment,
    ReviewCommentGroup,
    ReviewSettings,
)
from app.models.project import Chapter, Project
from app.schemas import APIResponse
from app.schemas.review import (
    GroupDecisionRequest,
    GroupDiscussRequest,
    ReaderAgentProfileRead,
    ReaderReviewRunCreate,
    ReaderReviewRunRead,
    ReviewCommentCreate,
    ReviewCommentGroupCreate,
    ReviewCommentGroupDetail,
    ReviewCommentGroupRead,
    ReviewCommentGroupUpdate,
    ReviewCommentListResponse,
    ReviewCommentRead,
    ReviewCommentReplyCreate,
    ReviewCommentUpdate,
    ReviewCommentWithReplies,
    ReviewSettingsRead,
    ReviewSettingsUpdate,
)


router = APIRouter(prefix="/reviews", tags=["reviews"])


# ============================================================
# 内部辅助
# ============================================================
SEVERITY_ORDER = {"low": 0, "medium": 1, "high": 2, "blocker": 3}


async def _get_or_create_settings(
    db: AsyncSession, project_id: int,
) -> ReviewSettings:
    settings = (await db.execute(
        select(ReviewSettings).where(ReviewSettings.project_id == project_id)
    )).scalar_one_or_none()
    if settings is None:
        # 缺省值跟 P6 spec §3.5 / seed 保持一致
        settings = ReviewSettings(
            project_id=project_id,
            auto_reader_review=True,
            auto_chief_triage=True,
            auto_discussion=True,
            retention_days=7,
            max_comments_per_chapter=50,
            max_reader_comments_per_run=5,
            min_severity_for_discussion="medium",
        )
        db.add(settings)
        await db.flush()
    return settings


def _resolve_expiry_days(
    settings: ReviewSettings, expires_in_days: int | None,
) -> datetime | None:
    """None = 永久保留 (系统消息); 否则用 retention_days 或用户传入."""
    if expires_in_days is None:
        return datetime.utcnow() + timedelta(days=settings.retention_days)
    if expires_in_days <= 0:
        return None  # 永久
    return datetime.utcnow() + timedelta(days=expires_in_days)


# ============================================================
# §6.1 评论列表
# ============================================================
@router.get("/comments", response_model=APIResponse[ReviewCommentListResponse])
async def list_comments(
    project_id: int | None = None,
    chapter_id: int | None = None,
    status: str | None = None,
    author_type: str | None = None,
    group_id: int | None = None,
    include_replies: bool = True,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> APIResponse[ReviewCommentListResponse]:
    """列评论. 默认只列顶层评论 (parent_id IS NULL), include_replies=true
    时附带直接子评论. group_by 不实现 (P1 spec 默认 'none')."""
    stmt = select(ReviewComment)
    if project_id is not None:
        stmt = stmt.where(ReviewComment.project_id == project_id)
    if chapter_id is not None:
        stmt = stmt.where(ReviewComment.chapter_id == chapter_id)
    if status is not None:
        stmt = stmt.where(ReviewComment.status == status)
    if author_type is not None:
        stmt = stmt.where(ReviewComment.author_type == author_type)
    if group_id is not None:
        stmt = stmt.where(ReviewComment.related_group_id == group_id)
    if not include_replies:
        stmt = stmt.where(ReviewComment.parent_id.is_(None))

    # total
    count_stmt = stmt.with_only_columns(ReviewComment.id)
    total = len((await db.execute(count_stmt)).scalars().all())

    # page
    page_stmt = (
        stmt.order_by(ReviewComment.created_at.desc())
        .limit(limit).offset(offset)
    )
    items = (await db.execute(page_stmt)).scalars().all()
    return {
        "ok": True,
        "data": ReviewCommentListResponse(
            items=[ReviewCommentRead.model_validate(c) for c in items],
            total=total,
        ),
    }


# ============================================================
# §6.2 用户发表评论
# ============================================================
@router.post(
    "/comments", response_model=APIResponse[ReviewCommentRead],
    status_code=201,
)
async def create_comment(
    body: ReviewCommentCreate, db: AsyncSession = Depends(get_db),
) -> APIResponse[ReviewCommentRead]:
    """创建评论. P1 只做 DB 写入, 触发 chief_triage 入队推迟到 P3."""
    # 校验 project 存在
    proj = await db.get(Project, body.project_id)
    if proj is None:
        raise not_found("Project", body.project_id)
    # 校验 chapter (如有)
    if body.chapter_id is not None:
        ch = await db.get(Chapter, body.chapter_id)
        if ch is None:
            raise not_found("Chapter", body.chapter_id)
        if ch.project_id != body.project_id:
            raise bad_request(
                "Chapter does not belong to project",
                suggestion="确保 chapter_id 跟 project_id 匹配",
            )
    # 校验 parent 评论 (如填)
    if body.parent_id is not None:
        parent = await db.get(ReviewComment, body.parent_id)
        if parent is None:
            raise not_found("ReviewComment", body.parent_id)
        if parent.project_id != body.project_id:
            raise bad_request("Parent comment belongs to a different project")

    settings = await _get_or_create_settings(db, body.project_id)

    # 上限检查: 同一 chapter 评论数
    if body.chapter_id is not None:
        n = (await db.execute(
            select(ReviewComment).where(
                ReviewComment.chapter_id == body.chapter_id,
            )
        )).scalars().all()
        if len(n) >= settings.max_comments_per_chapter:
            raise bad_request(
                f"Chapter reached max_comments_per_chapter "
                f"({settings.max_comments_per_chapter})",
                suggestion="7 天前的评论会自动清理, 或先合并相似评论入组",
            )

    expires_at = _resolve_expiry_days(settings, body.expires_in_days)

    comment = ReviewComment(
        project_id=body.project_id,
        chapter_id=body.chapter_id,
        chapter_version_id=body.chapter_version_id,
        parent_id=body.parent_id,
        target_type=body.target_type,
        author_type=body.author_type,
        author_label=body.author_label,
        agent_role_id=body.agent_role_id,
        content=body.content,
        evidence=body.evidence,
        rating=body.rating,
        tags=body.tags or [],
        weight_at_created=body.weight_at_created,
        status="new",
        priority=body.priority,
        expires_at=expires_at,
    )
    db.add(comment)
    await db.commit()
    await db.refresh(comment)
    return {"ok": True, "data": ReviewCommentRead.model_validate(comment)}


# ============================================================
# §6.2.1 评论详情 (含直接子评论)
# ============================================================
@router.get(
    "/comments/{comment_id}",
    response_model=APIResponse[ReviewCommentWithReplies],
)
async def get_comment(
    comment_id: int, db: AsyncSession = Depends(get_db),
) -> APIResponse[ReviewCommentWithReplies]:
    c = await db.get(ReviewComment, comment_id)
    if c is None:
        raise not_found("ReviewComment", comment_id)
    replies = (await db.execute(
        select(ReviewComment)
        .where(ReviewComment.parent_id == comment_id)
        .order_by(ReviewComment.created_at.asc())
    )).scalars().all()
    base = ReviewCommentRead.model_validate(c)
    return {
        "ok": True,
        "data": ReviewCommentWithReplies(
            **base.model_dump(),
            replies=[ReviewCommentRead.model_validate(r) for r in replies],
        ),
    }


# ============================================================
# §6.2.2 chief_agent 回复 (单独 endpoint, 自动挂 parent_id)
# ============================================================
@router.post(
    "/comments/{comment_id}/reply",
    response_model=APIResponse[ReviewCommentRead],
    status_code=201,
)
async def reply_to_comment(
    comment_id: int,
    body: ReviewCommentReplyCreate,
    author_label: str = "主 Agent",
    db: AsyncSession = Depends(get_db),
) -> APIResponse[ReviewCommentRead]:
    """chief_agent 风格回复, 自动填 author_type=chief_agent,
    parent_id=comment_id, status=replied. 父评论的 status 也同步更新为
    'replied'."""
    parent = await db.get(ReviewComment, comment_id)
    if parent is None:
        raise not_found("ReviewComment", comment_id)
    settings = await _get_or_create_settings(db, parent.project_id)

    reply = ReviewComment(
        project_id=parent.project_id,
        chapter_id=parent.chapter_id,
        chapter_version_id=parent.chapter_version_id,
        parent_id=comment_id,
        target_type=parent.target_type,
        author_type="chief_agent",
        author_label=author_label,
        agent_role_id=None,
        content=body.content,
        tags=body.tags or [],
        weight_at_created=1.0,
        status="replied",
        priority=parent.priority,
        expires_at=datetime.utcnow() + timedelta(days=settings.retention_days),
    )
    db.add(reply)
    # 父评论状态推进
    if parent.status == "new":
        parent.status = "replied"
    await db.commit()
    await db.refresh(reply)
    return {"ok": True, "data": ReviewCommentRead.model_validate(reply)}


# ============================================================
# §6.2.3 更新评论 (chief_agent 合并入组 / 调优先级)
# ============================================================
@router.patch(
    "/comments/{comment_id}",
    response_model=APIResponse[ReviewCommentRead],
)
async def update_comment(
    comment_id: int,
    body: ReviewCommentUpdate,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[ReviewCommentRead]:
    c = await db.get(ReviewComment, comment_id)
    if c is None:
        raise not_found("ReviewComment", comment_id)
    data = body.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(c, k, v)
    await db.commit()
    await db.refresh(c)
    return {"ok": True, "data": ReviewCommentRead.model_validate(c)}


# ============================================================
# §6.2.4 硬删 (P1: 给 admin / cleanup 用, 7 天过期自动删走 cleanup 端点)
# ============================================================
@router.delete("/comments/{comment_id}", response_model=APIResponse[dict])
async def delete_comment(
    comment_id: int, db: AsyncSession = Depends(get_db),
) -> APIResponse[dict]:
    c = await db.get(ReviewComment, comment_id)
    if c is None:
        raise not_found("ReviewComment", comment_id)
    await db.delete(c)
    await db.commit()
    return {"ok": True, "data": {"deleted": comment_id}}


# ============================================================
# §6.3 评论组列表
# ============================================================
@router.get(
    "/groups", response_model=APIResponse[list[ReviewCommentGroupRead]],
)
async def list_groups(
    project_id: int | None = None,
    chapter_id: int | None = None,
    status: str | None = None,
    severity: str | None = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> APIResponse[list[ReviewCommentGroupRead]]:
    stmt = select(ReviewCommentGroup)
    if project_id is not None:
        stmt = stmt.where(ReviewCommentGroup.project_id == project_id)
    if chapter_id is not None:
        stmt = stmt.where(ReviewCommentGroup.chapter_id == chapter_id)
    if status is not None:
        stmt = stmt.where(ReviewCommentGroup.status == status)
    if severity is not None:
        stmt = stmt.where(ReviewCommentGroup.severity == severity)
    stmt = stmt.order_by(
        ReviewCommentGroup.severity.desc(),
        ReviewCommentGroup.created_at.desc(),
    ).limit(limit).offset(offset)
    items = (await db.execute(stmt)).scalars().all()
    return {
        "ok": True,
        "data": [ReviewCommentGroupRead.model_validate(g) for g in items],
    }


# ============================================================
# §6.4 评论组详情
# ============================================================
@router.get(
    "/groups/{group_id}",
    response_model=APIResponse[ReviewCommentGroupDetail],
)
async def get_group(
    group_id: int, db: AsyncSession = Depends(get_db),
) -> APIResponse[ReviewCommentGroupDetail]:
    g = await db.get(ReviewCommentGroup, group_id)
    if g is None:
        raise not_found("ReviewCommentGroup", group_id)
    comment_ids = g.comment_ids or []
    comments: list[ReviewComment] = []
    if comment_ids:
        comments = (await db.execute(
            select(ReviewComment)
            .where(ReviewComment.id.in_(comment_ids))
            .order_by(ReviewComment.created_at.asc())
        )).scalars().all()
    base = ReviewCommentGroupRead.model_validate(g)
    return {
        "ok": True,
        "data": ReviewCommentGroupDetail(
            **base.model_dump(),
            comments=[ReviewCommentRead.model_validate(c) for c in comments],
        ),
    }


# ============================================================
# §6.4.1 手动创建评论组 (主 Agent 合并相似评论)
# ============================================================
@router.post(
    "/groups", response_model=APIResponse[ReviewCommentGroupRead],
    status_code=201,
)
async def create_group(
    body: ReviewCommentGroupCreate, db: AsyncSession = Depends(get_db),
) -> APIResponse[ReviewCommentGroupRead]:
    """主 Agent 合并相似评论成"问题包".

    自动把 comment_ids 里的评论的 status 改为 'grouped',
    related_group_id 指向新组."""
    proj = await db.get(Project, body.project_id)
    if proj is None:
        raise not_found("Project", body.project_id)

    # 校验所有 comment_ids 存在
    if body.comment_ids:
        comments = (await db.execute(
            select(ReviewComment)
            .where(ReviewComment.id.in_(body.comment_ids))
        )).scalars().all()
        found_ids = {c.id for c in comments}
        missing = set(body.comment_ids) - found_ids
        if missing:
            raise bad_request(
                f"Comment ids not found: {sorted(missing)}",
                suggestion="先建评论再合并入组",
            )
        # 跨 project 校验
        for c in comments:
            if c.project_id != body.project_id:
                raise bad_request(
                    f"Comment {c.id} belongs to project {c.project_id}, "
                    f"not {body.project_id}",
                )

    group = ReviewCommentGroup(
        project_id=body.project_id,
        chapter_id=body.chapter_id,
        chapter_version_id=body.chapter_version_id,
        title=body.title,
        summary=body.summary,
        comment_ids=body.comment_ids,
        severity=body.severity,
        status="new",
    )
    db.add(group)
    await db.flush()

    # 把评论标记为 grouped + related_group_id
    if body.comment_ids:
        from sqlalchemy import update
        await db.execute(
            update(ReviewComment)
            .where(ReviewComment.id.in_(body.comment_ids))
            .values(status="grouped", related_group_id=group.id)
        )

    await db.commit()
    await db.refresh(group)
    return {"ok": True, "data": ReviewCommentGroupRead.model_validate(group)}


# ============================================================
# §6.4.2 更新评论组
# ============================================================
@router.patch(
    "/groups/{group_id}",
    response_model=APIResponse[ReviewCommentGroupRead],
)
async def update_group(
    group_id: int,
    body: ReviewCommentGroupUpdate,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[ReviewCommentGroupRead]:
    g = await db.get(ReviewCommentGroup, group_id)
    if g is None:
        raise not_found("ReviewCommentGroup", group_id)
    data = body.model_dump(exclude_unset=True)
    # comment_ids 变更时同步评论的 related_group_id
    new_comment_ids = data.pop("comment_ids", None)
    for k, v in data.items():
        setattr(g, k, v)
    if new_comment_ids is not None:
        g.comment_ids = new_comment_ids
        from sqlalchemy import update
        # 老的: 移出
        if g.comment_ids:
            await db.execute(
                update(ReviewComment)
                .where(
                    ReviewComment.related_group_id == group_id,
                    ReviewComment.id.notin_(new_comment_ids),
                )
                .values(related_group_id=None, status="new")
            )
        # 新的: 挂上
        await db.execute(
            update(ReviewComment)
            .where(ReviewComment.id.in_(new_comment_ids))
            .values(status="grouped", related_group_id=group_id)
        )
    await db.commit()
    await db.refresh(g)
    return {"ok": True, "data": ReviewCommentGroupRead.model_validate(g)}


# ============================================================
# §6.4.3 转讨论 — P1 占位: 改 status + 标 discuss_pending
# P3 DiscussionBridge 实际创建 DiscussionSession
# ============================================================
@router.post(
    "/groups/{group_id}/discuss",
    response_model=APIResponse[ReviewCommentGroupRead],
)
async def discuss_group(
    group_id: int,
    body: GroupDiscussRequest,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[ReviewCommentGroupRead]:
    g = await db.get(ReviewCommentGroup, group_id)
    if g is None:
        raise not_found("ReviewCommentGroup", group_id)
    if g.status not in ("new", "discussing"):
        raise bad_request(
            f"Group status is '{g.status}', cannot discuss",
            suggestion="只有 new/discussing 状态可转讨论",
        )
    g.status = "discussing"
    # P1 占位: P3 再创建 DiscussionSession 并回填 discussion_session_id
    # P1 在 status 推进的同时把 note 写到 summary 末尾, 方便审计
    if body.note:
        g.summary = (g.summary or "") + f"\n\n[主 Agent 转讨论] {body.note}"
    await db.commit()
    await db.refresh(g)
    return {"ok": True, "data": ReviewCommentGroupRead.model_validate(g)}


# ============================================================
# §6.4.4 主 Agent 写裁决
# ============================================================
@router.post(
    "/groups/{group_id}/decide",
    response_model=APIResponse[ReviewCommentGroupRead],
)
async def decide_group(
    group_id: int,
    body: GroupDecisionRequest,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[ReviewCommentGroupRead]:
    g = await db.get(ReviewCommentGroup, group_id)
    if g is None:
        raise not_found("ReviewCommentGroup", group_id)
    if g.status not in ("new", "discussing", "decided"):
        raise bad_request(
            f"Group status is '{g.status}', cannot decide",
            suggestion="只有 new/discussing/decided 可写裁决 (decided 支持复盘覆盖)",
        )
    if body.decision in ("local_rewrite", "full_rewrite") and not body.rewrite_instruction:
        raise bad_request(
            f"decision={body.decision} 必须带 rewrite_instruction",
            suggestion="给 Rewriter 具体改法 (200~500 字)",
        )
    g.decision = body.model_dump()
    g.status = "rewrite_queued" if body.decision != "no_change" else "decided"
    # 同步更新评论状态
    from sqlalchemy import update
    if body.accepted_comment_ids:
        await db.execute(
            update(ReviewComment)
            .where(ReviewComment.id.in_(body.accepted_comment_ids))
            .values(status="accepted")
        )
    if body.rejected_comment_ids:
        await db.execute(
            update(ReviewComment)
            .where(ReviewComment.id.in_(body.rejected_comment_ids))
            .values(status="rejected")
        )
    await db.commit()
    await db.refresh(g)
    return {"ok": True, "data": ReviewCommentGroupRead.model_validate(g)}


# ============================================================
# §6.5 Review Settings
# ============================================================
@router.get(
    "/settings", response_model=APIResponse[ReviewSettingsRead],
)
async def get_settings(
    project_id: int = Query(..., ge=1),
    db: AsyncSession = Depends(get_db),
) -> APIResponse[ReviewSettingsRead]:
    settings = await _get_or_create_settings(db, project_id)
    await db.commit()
    return {"ok": True, "data": ReviewSettingsRead.model_validate(settings)}


@router.put(
    "/settings", response_model=APIResponse[ReviewSettingsRead],
)
async def update_settings(
    project_id: int = Query(..., ge=1),
    body: ReviewSettingsUpdate = ...,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[ReviewSettingsRead]:
    settings = await _get_or_create_settings(db, project_id)
    data = body.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(settings, k, v)
    await db.commit()
    await db.refresh(settings)
    return {"ok": True, "data": ReviewSettingsRead.model_validate(settings)}


# ============================================================
# §6.6 内部触发读者评审
# ============================================================
@router.post(
    "/runs", response_model=APIResponse[ReaderReviewRunRead],
    status_code=201,
)
async def create_run(
    body: ReaderReviewRunCreate, db: AsyncSession = Depends(get_db),
) -> APIResponse[ReaderReviewRunRead]:
    """P1: 只创建 ReaderReviewRun row (status=pending). P2 AgentRoleRunner
    实际拉起 5 reader (P2) + chief_comment_moderator (P3)."""
    proj = await db.get(Project, body.project_id)
    if proj is None:
        raise not_found("Project", body.project_id)
    ch = await db.get(Chapter, body.chapter_id)
    if ch is None:
        raise not_found("Chapter", body.chapter_id)
    if ch.project_id != body.project_id:
        raise bad_request(
            f"Chapter {body.chapter_id} does not belong to project {body.project_id}",
        )
    # 检查项目评论设置 (auto_reader_review=false 不阻止手动触发, 只警告)
    settings = await _get_or_create_settings(db, body.project_id)

    run = ReaderReviewRun(
        project_id=body.project_id,
        chapter_id=body.chapter_id,
        chapter_version_id=body.chapter_version_id,
        trigger=body.trigger,
        status="pending",
        reader_agent_keys=[
            "reader_hook", "reader_emotion", "reader_logic",
            "reader_commercial", "reader_toxic",
        ],
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)
    return {"ok": True, "data": ReaderReviewRunRead.model_validate(run)}


@router.get(
    "/runs", response_model=APIResponse[list[ReaderReviewRunRead]],
)
async def list_runs(
    project_id: int | None = None,
    chapter_id: int | None = None,
    status: str | None = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> APIResponse[list[ReaderReviewRunRead]]:
    stmt = select(ReaderReviewRun)
    if project_id is not None:
        stmt = stmt.where(ReaderReviewRun.project_id == project_id)
    if chapter_id is not None:
        stmt = stmt.where(ReaderReviewRun.chapter_id == chapter_id)
    if status is not None:
        stmt = stmt.where(ReaderReviewRun.status == status)
    stmt = stmt.order_by(
        ReaderReviewRun.created_at.desc()
    ).limit(limit).offset(offset)
    items = (await db.execute(stmt)).scalars().all()
    return {
        "ok": True,
        "data": [ReaderReviewRunRead.model_validate(r) for r in items],
    }


@router.get(
    "/runs/{run_id}", response_model=APIResponse[ReaderReviewRunRead],
)
async def get_run(
    run_id: int, db: AsyncSession = Depends(get_db),
) -> APIResponse[ReaderReviewRunRead]:
    r = await db.get(ReaderReviewRun, run_id)
    if r is None:
        raise not_found("ReaderReviewRun", run_id)
    return {"ok": True, "data": ReaderReviewRunRead.model_validate(r)}


# ============================================================
# Reader Agent Profile 列表 (P1: 矩阵前端会要这个)
# ============================================================
@router.get(
    "/reader-profiles",
    response_model=APIResponse[list[ReaderAgentProfileRead]],
)
async def list_reader_profiles(
    enabled_only: bool = False,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[list[ReaderAgentProfileRead]]:
    stmt = select(ReaderAgentProfile)
    if enabled_only:
        stmt = stmt.where(ReaderAgentProfile.enabled.is_(True))
    stmt = stmt.order_by(ReaderAgentProfile.reader_key.asc())
    items = (await db.execute(stmt)).scalars().all()
    return {
        "ok": True,
        "data": [ReaderAgentProfileRead.model_validate(p) for p in items],
    }


# ============================================================
# 7 天过期清理 (P1: 给测试 / 手动触发用, P4 worker 也定时调)
# ============================================================
@router.post(
    "/cleanup", response_model=APIResponse[dict],
)
async def cleanup_expired(
    project_id: int | None = None,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[dict]:
    """删 expires_at < now() AND author_type != 'system' 的评论.
    采纳统计已经在 accepted 时写入 ReaderAgentProfile, 删原评论安全.
    system 类型评论 expires_at 是 NULL (永久), 不会被删."""
    stmt = delete(ReviewComment).where(
        ReviewComment.expires_at.is_not(None),
        ReviewComment.expires_at < datetime.utcnow(),
        ReviewComment.author_type != "system",
    )
    if project_id is not None:
        stmt = stmt.where(ReviewComment.project_id == project_id)
    result = await db.execute(stmt)
    await db.commit()
    return {
        "ok": True,
        "data": {"deleted": result.rowcount or 0},
    }
