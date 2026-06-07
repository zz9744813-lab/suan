"""P6 §6: 评论/评论组/读者评审 — REST API.

P1 范围 (已实现):
  - 17 端点, 全部直接读写 DB
  - 不调 LLM

P3 增强 (本文件内):
  - discuss_group: 调 DiscussionBridge 真创建 DiscussionSession (替代 P1 占位)
  - decide_group:  调 WeightService.bump_for_comment 更新读者权重
  - 新增 trigger_triage: 手动触发 chief_comment_moderator 分流
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.errors import bad_request, not_found
from app.models.agent_role import AgentRole
from app.models.comment_review import (
    ReaderAgentProfile,
    ReaderReviewRun,
    ReviewComment,
    ReviewCommentGroup,
    ReviewSettings,
)
from app.models.project import Chapter, ChapterVersion, Project
from app.schemas import APIResponse
from app.schemas.review import (
    AgentAutoCreateRequest,
    AgentAutoCreateResponse,
    GroupDecisionRequest,
    GroupDiscussRequest,
    ReaderAgentProfileRead,
    ReaderReviewRunCreate,
    ReaderReviewRunRead,
    ReaderReviewQuickGenerateResponse,
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
from app.services.review import (
    CommentTriageService,
    DiscussionBridge,
    TriageOutcome,
    WeightService,
    get_comment_triage_service,
    get_discussion_bridge,
    get_weight_service,
)
from app.services.audit_service import log_review_action


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


def _quick_reader_comments(chapter: Chapter, content: str) -> list[dict[str, Any]]:
    excerpt = (content or "").strip().replace("\r", "")[:180]
    if not excerpt:
        excerpt = "当前章节暂无可评审正文，建议先生成正文后再发起正式评审。"
    word_count = len(content or "")
    density_hint = "篇幅偏短，建议补足场景推进和人物反应。" if word_count < 1200 else "篇幅充足，可以重点检查节奏和信息密度。"
    return [
        {
            "key": "reader_hook",
            "label": "钩子读者",
            "dimension": "开篇钩子 / 追读欲",
            "priority": 72,
            "tags": ["钩子", "追读"],
            "content": f"第 {chapter.chapter_no} 章《{chapter.title}》的追读点需要更明确。当前片段：{excerpt}\n\n建议：在章末或关键转折处增加一个更锋利的问题、反差或危机，让读者有'下一章必须看'的理由。{density_hint}",
            "rating": {"score": 74, "dimension": "hook"},
        },
        {
            "key": "reader_emotion",
            "label": "情绪读者",
            "dimension": "情绪共鸣 / 爽感",
            "priority": 68,
            "tags": ["情绪", "爽点"],
            "content": f"这一章的情绪落点可以再放大。读者需要更清楚地知道主角此刻'想要什么、害怕什么、赢了什么'。\n\n建议：补一两处内心反应或旁人反馈，把胜负感、压迫感、委屈感/释放感写实。",
            "rating": {"score": 76, "dimension": "emotion"},
        },
        {
            "key": "reader_logic",
            "label": "逻辑读者",
            "dimension": "因果 / 设定一致性",
            "priority": 80,
            "tags": ["逻辑", "因果"],
            "content": f"请重点复查本章事件的因果链：角色为什么这么做、信息从哪里来、能力/资源是否突然出现。\n\n建议：如果有关键行动，补一句动机或前置信息，避免读者觉得是作者强推剧情。",
            "rating": {"score": 71, "dimension": "logic"},
        },
        {
            "key": "reader_commercial",
            "label": "商业读者",
            "dimension": "网文节奏 / 付费转化",
            "priority": 75,
            "tags": ["商业", "节奏"],
            "content": f"商业节奏上建议检查：本章是否有明确目标、明确阻力、明确结果。\n\n如果本章主要是铺垫，建议加入一个小兑现点；如果是高潮章，建议减少解释，增加行动和反馈。",
            "rating": {"score": 73, "dimension": "commercial"},
        },
        {
            "key": "reader_toxic",
            "label": "毒点读者",
            "dimension": "弃读风险 / 雷点",
            "priority": 86,
            "tags": ["毒点", "弃读风险"],
            "content": f"潜在弃读风险：解释过多、目标不清、角色反应弱、冲突兑现不足。\n\n建议：删掉重复说明，把关键信息交给动作、对话或冲突结果呈现；尤其注意章中不要让读者长时间看不到推进。",
            "rating": {"score": 69, "dimension": "toxic"},
        },
    ]


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
    # P6 §5.4: 评论写入后, 自动入队 comment_triage 任务
    # (auto_chief_triage 开关在 ReviewQueueService 内部判断, 关闭时静默跳过)
    try:
        from app.services.review import (
            ENQUEUE_SOURCE_AUTO_COMMENT,
            get_review_queue,
        )
        # 重新开 session, queue 走自己的 session_scope 避免污染请求 session
        from app.core.database import session_scope
        async with session_scope() as enq_db:
            await get_review_queue().enqueue_triage(
                enq_db,
                project_id=comment.project_id,
                chapter_id=comment.chapter_id,
                source=ENQUEUE_SOURCE_AUTO_COMMENT,
            )
    except Exception as exc:  # 入队失败不阻挡评论写入成功
        # 用 logger 写 stderr, 留 audit
        import logging
        logging.getLogger(__name__).warning(
            "评论 %s 入队 comment_triage 失败: %s",
            comment.id, str(exc),
        )
    return {"ok": True, "data": ReviewCommentRead.model_validate(comment)}


# ============================================================
# §6.2.0.1 触发主 Agent 分流 (P3 §5.4)
# 手动测试 / 内部 worker 触发, 拉取 project / chapter 下所有 status='new'
# 评论调 chief_comment_moderator 分流. 评论流已经在 POST /comments
# 自动入队, 这个端点主要给"重跑"和"管理面板"用.
# ============================================================
class TriageTriggerRequest(BaseModel):
    project_id: int = Field(..., ge=1)
    chapter_id: int | None = None


class TriageItemOut(BaseModel):
    comment_id: int
    action: str
    success: bool
    detail: str
    error: str | None = None


class TriageTriggerResponse(BaseModel):
    project_id: int
    chapter_id: int | None
    new_comment_count: int
    reply_count: int
    group_count: int
    discuss_count: int
    ignore_count: int
    error_count: int
    error: str | None
    items: list[TriageItemOut]
    triage_run_id: int | None  # 调 chief 的 AgentRun.id


@router.post(
    "/triage",
    response_model=APIResponse[TriageTriggerResponse],
    status_code=200,
)
async def trigger_triage(
    body: TriageTriggerRequest,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[TriageTriggerResponse]:
    """P3 §5.4: 触发主 Agent (chief_comment_moderator) 分流.

    拉 project/chapter 下所有 status='new' 的评论, 调 chief 决策
    (reply/group/discuss/ignore), 写主 Agent reply, 合并/触发讨论.
    """
    settings = await _get_or_create_settings(db, body.project_id)
    if not settings.auto_chief_triage:
        raise bad_request(
            "auto_chief_triage 已关闭, 不允许自动分流",
            suggestion="在 ReviewSettings 打开 auto_chief_triage 后再试",
        )
    service = get_comment_triage_service()
    outcome = await service.run_for_chapter(
        db, project_id=body.project_id, chapter_id=body.chapter_id,
    )
    await db.commit()
    return {
        "ok": True,
        "data": TriageTriggerResponse(
            project_id=outcome.project_id,
            chapter_id=outcome.chapter_id,
            new_comment_count=outcome.new_comment_count,
            reply_count=outcome.reply_count,
            group_count=outcome.group_count,
            discuss_count=outcome.discuss_count,
            ignore_count=outcome.ignore_count,
            error_count=outcome.error_count,
            error=outcome.error,
            items=[
                TriageItemOut(
                    comment_id=i.comment_id, action=i.action,
                    success=i.success, detail=i.detail, error=i.error,
                )
                for i in outcome.items
            ],
            triage_run_id=outcome.triage_result.run_id if outcome.triage_result else None,
        ),
    }


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
    # ── 审计 ─────────────────────────────────────────────
    await log_review_action(
        db,
        actor_type="agent", actor_key="chief_agent",
        project_id=parent.project_id,
        chapter_id=parent.chapter_id,
        comment_id=comment_id, action="reply", decision=None,
    )
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
    # ── 审计 ──────────────────────────────────────────
    await log_review_action(
        db,
        actor_type="agent" if c.agent_role_id else "user",
        actor_key=None,
        project_id=c.project_id,
        chapter_id=c.chapter_id,
        comment_id=comment_id,
        action=f"update:{','.join(data.keys())}",
        decision=None,
    )
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
# §6.4.3 转讨论 — P3 实装: 调 DiscussionBridge 真创建 DiscussionSession
# P1 阶段是占位 (改 status), P3 这一步补 DiscussionSession 占位 + 入队
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

    # P3 增强: 调 DiscussionBridge 真创建 DiscussionSession
    if g.discussion_session_id is None:
        bridge = get_discussion_bridge()
        session = await bridge.create_from_group(db, g)
        # g.status / g.discussion_session_id 由 bridge 内部写好
        # note 写到 summary 末尾 (兼容 P1 行为)
        if body.note:
            g.summary = (g.summary or "") + f"\n\n[主 Agent 转讨论] {body.note}"
        await db.commit()
        await db.refresh(g)
    else:
        # 已存在 session, 只追加 note
        if body.note:
            g.summary = (g.summary or "") + f"\n\n[主 Agent 转讨论] {body.note}"
        await db.commit()
        await db.refresh(g)
    return {"ok": True, "data": ReviewCommentGroupRead.model_validate(g)}


# ============================================================
# §6.4.4 主 Agent 写裁决
# P3 增强: 写 decision 后, 调 WeightService.bump_for_comment 更新
#          每条 reader_agent 评论的权重 (accept +0.08, reject -0.03)
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

    # P3 增强: 更新读者权重
    weight_service = get_weight_service()
    bump_results: list[dict[str, Any]] = []
    for cid in body.accepted_comment_ids:
        r = await weight_service.bump_for_comment(db, comment_id=cid, decision="accepted")
        if r is not None:
            bump_results.append({
                "comment_id": cid, "decision": r.decision,
                "reader_key": r.reader_key,
                "old_weight": r.old_weight, "new_weight": r.new_weight,
            })
    for cid in body.rejected_comment_ids:
        r = await weight_service.bump_for_comment(db, comment_id=cid, decision="rejected")
        if r is not None:
            bump_results.append({
                "comment_id": cid, "decision": r.decision,
                "reader_key": r.reader_key,
                "old_weight": r.old_weight, "new_weight": r.new_weight,
            })

    # 把权重变更记到 decision JSON 末尾 (审计用)
    if bump_results:
        existing = dict(g.decision or {})
        existing["weight_bumps"] = bump_results
        g.decision = existing

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


@router.post(
    "/runs/quick-generate",
    response_model=APIResponse[ReaderReviewQuickGenerateResponse],
    status_code=201,
)
async def quick_generate_reader_review(
    body: ReaderReviewRunCreate, db: AsyncSession = Depends(get_db),
) -> APIResponse[ReaderReviewQuickGenerateResponse]:
    """立即生成一轮可用的五维读者反馈。

    这是读者模块的轻量实装入口: 不等待后台 LLM runner,
    直接把 5 个读者维度写入评论表, 前端即可采纳/驳回/转分流。
    后续替换为真正 reader agent 时可保持前端 API 不变。
    """
    proj = await db.get(Project, body.project_id)
    if proj is None:
        raise not_found("Project", body.project_id)
    ch = await db.get(Chapter, body.chapter_id)
    if ch is None:
        raise not_found("Chapter", body.chapter_id)
    if ch.project_id != body.project_id:
        raise bad_request(f"Chapter {body.chapter_id} does not belong to project {body.project_id}")

    version = None
    if body.chapter_version_id:
        version = await db.get(ChapterVersion, body.chapter_version_id)
    if version is None:
        versions = (await db.execute(
            select(ChapterVersion)
            .where(ChapterVersion.chapter_id == ch.id)
            .order_by(ChapterVersion.version_kind.desc(), ChapterVersion.version_no.desc(), ChapterVersion.id.desc())
        )).scalars().all()
        for kind in ("final", "rewrite", "draft"):
            candidates = [v for v in versions if v.version_kind == kind or v.version_kind.startswith(kind)]
            if candidates:
                version = candidates[0]
                break
        if version is None and versions:
            version = versions[0]

    settings = await _get_or_create_settings(db, body.project_id)
    specs = _quick_reader_comments(ch, version.content if version else "")
    run = ReaderReviewRun(
        project_id=body.project_id,
        chapter_id=body.chapter_id,
        chapter_version_id=version.id if version else body.chapter_version_id,
        trigger=body.trigger,
        status="succeeded",
        reader_agent_keys=[s["key"] for s in specs],
        started_at=datetime.utcnow(),
        finished_at=datetime.utcnow(),
    )
    db.add(run)
    await db.flush()

    comments: list[ReviewComment] = []
    for spec in specs[: settings.max_reader_comments_per_run]:
        comment = ReviewComment(
            project_id=body.project_id,
            chapter_id=body.chapter_id,
            chapter_version_id=version.id if version else body.chapter_version_id,
            target_type="chapter",
            author_type="reader_agent",
            author_label=spec["label"],
            agent_role_id=None,
            content=spec["content"],
            evidence=[{"chapter_id": ch.id, "chapter_no": ch.chapter_no, "excerpt": (version.content if version else "")[:220]}],
            rating=spec["rating"],
            tags=spec["tags"],
            weight_at_created=1.0,
            status="new",
            priority=spec["priority"],
            expires_at=datetime.utcnow() + timedelta(days=settings.retention_days),
        )
        db.add(comment)
        comments.append(comment)
    await db.flush()
    run.generated_comment_ids = [c.id for c in comments]
    await db.commit()
    await db.refresh(run)
    for comment in comments:
        await db.refresh(comment)
    return {
        "ok": True,
        "data": ReaderReviewQuickGenerateResponse(
            run=ReaderReviewRunRead.model_validate(run),
            comments=[ReviewCommentRead.model_validate(c) for c in comments],
        ),
    }


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


# ============================================================
# §6.7 Agent 自动创建评论 (评论自动流 S5-T1)
# ============================================================
@router.post(
    "/auto-create",
    response_model=APIResponse[AgentAutoCreateResponse],
    status_code=201,
    summary="Agent 任务完成后自动将输出写入评论区",
)
async def auto_create_review(
    body: AgentAutoCreateRequest,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[AgentAutoCreateResponse]:
    """Agent 任务 (Critic / reader_* 等) 完成后, 自动将输出写入评论区.

    逻辑:
      1. 校验 project / chapter 存在
      2. 按 agent_key 查找 AgentRole → agent_role_id + author_label
      3. 判定 author_type (reader_* → "reader_agent", 其他 → "chief_agent")
      4. 写 ReviewComment (status=new)
      5. 自动入队 comment_triage (同 POST /comments)
      6. 返回创建的评论
    """
    # 1. 校验 project
    proj = await db.get(Project, body.project_id)
    if proj is None:
        raise not_found("Project", body.project_id)
    # 2. 校验 chapter
    if body.chapter_id is not None:
        ch = await db.get(Chapter, body.chapter_id)
        if ch is None:
            raise not_found("Chapter", body.chapter_id)
        if ch.project_id != body.project_id:
            raise bad_request("Chapter does not belong to project")

    # 3. 查找 AgentRole
    role_row = (
        await db.execute(
            select(AgentRole).where(AgentRole.key == body.agent_key)
        )
    ).scalar_one_or_none()
    agent_role_id = role_row.id if role_row else None
    author_label = role_row.display_name if role_row else body.agent_key

    # 4. 判定 author_type
    if body.agent_key.startswith("reader_"):
        author_type: AuthorType = "reader_agent"
    else:
        author_type = "chief_agent"

    settings = await _get_or_create_settings(db, body.project_id)

    # 5. 上限检查
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
            )

    expires_at = _resolve_expiry_days(settings, None)

    comment = ReviewComment(
        project_id=body.project_id,
        chapter_id=body.chapter_id,
        chapter_version_id=body.chapter_version_id,
        parent_id=None,
        target_type="chapter",
        author_type=author_type,
        author_label=author_label,
        agent_role_id=agent_role_id,
        content=body.content,
        evidence=None,
        rating=None,
        tags=body.tags or [],
        weight_at_created=1.0,
        status="new",
        priority=body.priority,
        expires_at=expires_at,
    )
    db.add(comment)
    await db.flush()  # 拿到 comment.id

    # 6. 自动入队 comment_triage (同 create_comment 逻辑)
    triage_enqueued = False
    triage_run_id: int | None = None
    try:
        from app.services.review import (
            ENQUEUE_SOURCE_AUTO_COMMENT,
            get_review_queue,
        )
        from app.core.database import session_scope
        async with session_scope() as enq_db:
            await get_review_queue().enqueue_triage(
                enq_db,
                project_id=comment.project_id,
                chapter_id=comment.chapter_id,
                source=ENQUEUE_SOURCE_AUTO_COMMENT,
            )
        triage_enqueued = True
    except Exception as _exc:
        import logging
        logging.getLogger(__name__).warning(
            "auto-create 评论 %s 入队 comment_triage 失败: %s",
            comment.id, _exc,
        )

    await db.commit()
    await db.refresh(comment)

    return {
        "ok": True,
        "data": AgentAutoCreateResponse(
            comment=ReviewCommentRead.model_validate(comment),
            triage_enqueued=triage_enqueued,
            triage_run_id=triage_run_id,
        ),
    }


# ============================================================
# §5 读者 Agent 编辑中心 API
# ============================================================

class ReaderAgentPatch(BaseModel):
    """PATCH /reviews/readers/{reader_key} 的更新字段."""
    display_name: str | None = Field(None, min_length=1, max_length=120)
    enabled: bool | None = None
    weight: float | None = Field(None, ge=0.5, le=2.5)
    dimension: str | None = Field(None, min_length=1, max_length=80)


@router.get("/readers", response_model=APIResponse[list[ReaderAgentProfileRead]])
async def list_reader_agents(
    db: AsyncSession = Depends(get_db),
):
    """列出所有读者 Agent 配置."""
    rows = (await db.execute(
        select(ReaderAgentProfile).order_by(ReaderAgentProfile.id)
    )).scalars().all()
    return {
        "ok": True,
        "data": [ReaderAgentProfileRead.model_validate(r) for r in rows],
    }


@router.get(
    "/readers/{reader_key}",
    response_model=APIResponse[ReaderAgentProfileRead],
)
async def get_reader_agent(
    reader_key: str,
    db: AsyncSession = Depends(get_db),
):
    """获取单个读者 Agent 配置."""
    row = (await db.execute(
        select(ReaderAgentProfile).where(
            ReaderAgentProfile.reader_key == reader_key,
        )
    )).scalar_one_or_none()
    if row is None:
        raise not_found("ReaderAgentProfile", reader_key)
    return {"ok": True, "data": ReaderAgentProfileRead.model_validate(row)}


@router.patch(
    "/readers/{reader_key}",
    response_model=APIResponse[ReaderAgentProfileRead],
)
async def update_reader_agent(
    reader_key: str,
    body: ReaderAgentPatch,
    db: AsyncSession = Depends(get_db),
):
    """更新读者 Agent 配置 (display_name, enabled, weight, dimension 等)."""
    row = (await db.execute(
        select(ReaderAgentProfile).where(
            ReaderAgentProfile.reader_key == reader_key,
        )
    )).scalar_one_or_none()
    if row is None:
        raise not_found("ReaderAgentProfile", reader_key)

    data = body.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(row, k, v)
    await db.flush()
    return {"ok": True, "data": ReaderAgentProfileRead.model_validate(row)}


@router.get(
    "/readers/{reader_key}/comments",
    response_model=APIResponse[list[dict]],
)
async def get_reader_comments(
    reader_key: str,
    limit: int = Query(20, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    """获取指定读者最近的评论."""
    # 先找 reader_key 对应的 agent_role_id
    profile = (await db.execute(
        select(ReaderAgentProfile).where(
            ReaderAgentProfile.reader_key == reader_key,
        )
    )).scalar_one_or_none()
    if profile is None:
        raise not_found("ReaderAgentProfile", reader_key)

    comments = (await db.execute(
        select(ReviewComment).where(
            ReviewComment.agent_role_id == profile.agent_role_id,
            ReviewComment.author_type == "reader_agent",
        ).order_by(ReviewComment.created_at.desc()).limit(limit)
    )).scalars().all()

    return {
        "ok": True,
        "data": [
            {
                "id": c.id,
                "project_id": c.project_id,
                "chapter_id": c.chapter_id,
                "content": c.content[:500],
                "status": c.status,
                "rating": c.rating,
                "tags": c.tags,
                "priority": c.priority,
                "created_at": c.created_at.isoformat() if c.created_at else None,
            }
            for c in comments
        ],
    }


@router.get(
    "/readers/{reader_key}/stats",
    response_model=APIResponse[dict],
)
async def get_reader_stats(
    reader_key: str,
    db: AsyncSession = Depends(get_db),
):
    """获取指定读者的统计 (adopted/rejected/comment_count 等)."""
    row = (await db.execute(
        select(ReaderAgentProfile).where(
            ReaderAgentProfile.reader_key == reader_key,
        )
    )).scalar_one_or_none()
    if row is None:
        raise not_found("ReaderAgentProfile", reader_key)

    return {
        "ok": True,
        "data": {
            "reader_key": row.reader_key,
            "display_name": row.display_name,
            "dimension": row.dimension,
            "weight": row.weight,
            "adopted_count": row.adopted_count,
            "rejected_count": row.rejected_count,
            "generated_comment_count": row.generated_comment_count,
            "enabled": row.enabled,
            "last_used_at": row.last_used_at.isoformat() if row.last_used_at else None,
            "adoption_rate": round(
                row.adopted_count / row.generated_comment_count, 4,
            ) if row.generated_comment_count > 0 else 0.0,
        },
    }


# ============================================================
# §7 评审自动流程状态 API
# ============================================================

@router.get(
    "/projects/{project_id}/auto-flow",
    response_model=APIResponse[dict],
)
async def get_auto_flow_status(
    project_id: int,
    chapter_id: int | None = None,
    db: AsyncSession = Depends(get_db),
):
    """返回指定项目/章节的评审自动流程状态.

    聚合 AgentTask, ReviewComment, ReviewCommentGroup, DiscussionSession 等表,
    返回 { state, steps: [...], debug_actions: [...] }.
    """
    from app.models.task import AgentTask
    from app.models.discussion import DiscussionSession as DS

    # 校验 project
    proj = await db.get(Project, project_id)
    if proj is None:
        raise not_found("Project", project_id)

    # 1. AgentTask 状态
    task_stmt = select(AgentTask).where(AgentTask.project_id == project_id)
    if chapter_id is not None:
        task_stmt = task_stmt.where(AgentTask.chapter_id == chapter_id)
    task_stmt = task_stmt.order_by(AgentTask.created_at.desc()).limit(10)
    tasks = (await db.execute(task_stmt)).scalars().all()

    # 2. ReviewComment 状态
    comment_stmt = select(ReviewComment).where(
        ReviewComment.project_id == project_id,
    )
    if chapter_id is not None:
        comment_stmt = comment_stmt.where(
            ReviewComment.chapter_id == chapter_id,
        )
    comment_stmt = comment_stmt.order_by(
        ReviewComment.created_at.desc(),
    ).limit(20)
    comments = (await db.execute(comment_stmt)).scalars().all()

    # 3. ReviewCommentGroup 状态
    group_stmt = select(ReviewCommentGroup).where(
        ReviewCommentGroup.project_id == project_id,
    )
    if chapter_id is not None:
        group_stmt = group_stmt.where(
            ReviewCommentGroup.chapter_id == chapter_id,
        )
    group_stmt = group_stmt.order_by(
        ReviewCommentGroup.created_at.desc(),
    ).limit(10)
    groups = (await db.execute(group_stmt)).scalars().all()

    # 4. DiscussionSession 状态
    disc_stmt = select(DS).where(DS.project_id == project_id)
    disc_stmt = disc_stmt.order_by(DS.created_at.desc()).limit(5)
    discussions = (await db.execute(disc_stmt)).scalars().all()

    # 推断整体 state
    has_running_task = any(t.status in ("pending", "running") for t in tasks)
    has_undecided_group = any(g.status in ("new", "discussing") for g in groups)
    has_running_disc = any(d.status == "running" for d in discussions)

    if has_running_task or has_running_disc:
        state = "running"
    elif has_undecided_group:
        state = "pending_decision"
    elif any(t.status == "failed" for t in tasks):
        state = "error"
    else:
        state = "idle"

    # 构建 steps
    steps: list[dict[str, Any]] = []

    # 读者评审步
    reader_runs = [c for c in comments if c.author_type == "reader_agent"]
    if reader_runs:
        steps.append({
            "step": "reader_review",
            "status": "completed",
            "comment_count": len(reader_runs),
            "latest_at": max(
                c.created_at for c in reader_runs
            ).isoformat() if reader_runs else None,
        })

    # chief 分流步
    chief_replies = [c for c in comments if c.author_type == "chief_agent"]
    if chief_replies:
        steps.append({
            "step": "chief_triage",
            "status": "completed",
            "reply_count": len(chief_replies),
            "latest_at": max(
                c.created_at for c in chief_replies
            ).isoformat() if chief_replies else None,
        })

    # 评论组合并步
    if groups:
        steps.append({
            "step": "comment_grouping",
            "status": "completed",
            "group_count": len(groups),
            "undecided": sum(
                1 for g in groups if g.status in ("new", "discussing")
            ),
        })

    # 讨论步
    if discussions:
        steps.append({
            "step": "discussion",
            "status": (
                "running" if has_running_disc else "completed"
            ),
            "session_count": len(discussions),
        })

    # 决策/重写步
    rewrite_groups = [
        g for g in groups if g.status == "rewrite_queued"
    ]
    if rewrite_groups:
        steps.append({
            "step": "rewrite",
            "status": "pending",
            "group_count": len(rewrite_groups),
        })

    # debug_actions
    debug_actions: list[dict[str, str]] = []
    if has_undecided_group:
        debug_actions.append({
            "action": "decide_group",
            "label": "裁决待定评论组",
        })
    if has_running_task:
        debug_actions.append({
            "action": "check_tasks",
            "label": "查看运行中的任务",
        })
    if any(t.status == "failed" for t in tasks):
        debug_actions.append({
            "action": "retry_failed",
            "label": "重试失败任务",
        })

    return {
        "ok": True,
        "data": {
            "state": state,
            "project_id": project_id,
            "chapter_id": chapter_id,
            "steps": steps,
            "debug_actions": debug_actions,
            "task_count": len(tasks),
            "comment_count": len(comments),
            "group_count": len(groups),
            "discussion_count": len(discussions),
        },
    }
