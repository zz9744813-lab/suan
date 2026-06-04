"""P3: CommentTriageService — 主 Agent (chief_comment_moderator) 自动接入评论.

工作流 (P6 spec §4.3):
  1. 拉取同项目 / 同章节下 status='new' 的评论
  2. 调 chief_comment_moderator (用 chief_comment_triage prompt) 决策分流
  3. 对每条新评论执行 4 种 action:
     - reply   → 写 chief_agent ReviewComment (parent_id=comment_id, status=replied)
     - group   → 创建或加入 ReviewCommentGroup, comment.status='grouped'
     - discuss → 创建 ReviewCommentGroup, 调 DiscussionBridge 触发讨论,
                 comment.status='discussing', 回填 group.discussion_session_id
     - ignore  → comment.status='ignored'

入口:
  CommentTriageService.run_for_chapter(db, *, project_id, chapter_id=None)
  → TriageOutcome (run_id, reply_count, group_count, discuss_count, ignore_count)

设计要点:
  - 不调 chief_comment_decision (那是 group 讨论完成后的裁决)
  - 不调 WeightService (那是 decision 后, 跟 triage 无关)
  - 失败隔离: 单条 triage item 失败不影响其他 item
  - 重入安全: run 完后所有 status='new' 的评论都推进 (replied / grouped /
    discussing / ignored), 下次再跑就不会重复处理
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import not_found
from app.models.agent_role import AgentRole
from app.models.comment_review import (
    ReviewComment,
    ReviewCommentGroup,
    ReviewSettings,
)
from app.models.project import Project
from app.services.review.agent_role_runner import (
    AgentRoleRunner,
    AgentRoleRunResult,
    get_agent_role_runner,
)
from app.services.review.discussion_bridge import (
    DiscussionBridge,
    get_discussion_bridge,
)

logger = logging.getLogger(__name__)


CHIEF_COMMENT_MODERATOR_KEY = "chief_comment_moderator"
TRIAGE_TEMPLATE_KEY = "chief_comment_triage"

# action 类型, 跟 chief_comment_triage prompt 的输出 schema 一致
ACTION_REPLY = "reply"
ACTION_GROUP = "group"
ACTION_DISCUSS = "discuss"
ACTION_IGNORE = "ignore"
VALID_ACTIONS = frozenset({ACTION_REPLY, ACTION_GROUP, ACTION_DISCUSS, ACTION_IGNORE})

# severity → 数值, 决定 min_severity_for_discussion 阈值
SEVERITY_RANK = {"low": 0, "medium": 1, "high": 2, "blocker": 3}


@dataclass
class TriageItemOutcome:
    """单条 triage item 的执行结果."""

    comment_id: int
    action: str  # 跟 chief_agent 输出 action 一致
    success: bool
    detail: str  # 写入的 ReviewCommentGroup id / 主 Agent reply id / reason
    error: str | None = None


@dataclass
class TriageOutcome:
    """CommentTriageService.run_for_chapter 的返回结果."""

    project_id: int
    chapter_id: int | None
    new_comment_count: int  # 拉取到的新评论数
    triage_result: AgentRoleRunResult | None  # AgentRoleRunner 结果 (parse 失败时 parsed 空)
    items: list[TriageItemOutcome] = field(default_factory=list)
    reply_count: int = 0
    group_count: int = 0
    discuss_count: int = 0
    ignore_count: int = 0
    error_count: int = 0
    error: str | None = None


class CommentTriageService:
    def __init__(
        self,
        runner: AgentRoleRunner | None = None,
        bridge: DiscussionBridge | None = None,
    ) -> None:
        self.runner = runner or get_agent_role_runner()
        self.bridge = bridge or get_discussion_bridge()

    async def run_for_chapter(
        self,
        db: AsyncSession,
        *,
        project_id: int,
        chapter_id: int | None = None,
    ) -> TriageOutcome:
        """拉取 project / chapter 下 status='new' 评论, 调主 Agent 分流.

        Returns TriageOutcome (含每条 item 的执行结果).
        """
        outcome = TriageOutcome(
            project_id=project_id, chapter_id=chapter_id,
            new_comment_count=0, triage_result=None,
        )

        # 0. 校验项目
        proj = await db.get(Project, project_id)
        if proj is None:
            raise not_found("Project", str(project_id))

        # 1. 拉新评论 (用户 + 读者 Agent, 主 Agent reply / system 跳过)
        new_q = select(ReviewComment).where(
            ReviewComment.project_id == project_id,
            ReviewComment.status == "new",
            ReviewComment.author_type.in_(("user", "reader_agent")),
        )
        if chapter_id is not None:
            new_q = new_q.where(ReviewComment.chapter_id == chapter_id)
        new_q = new_q.order_by(
            ReviewComment.priority.desc(),
            ReviewComment.created_at.asc(),
        )
        new_comments = (await db.execute(new_q)).scalars().all()
        outcome.new_comment_count = len(new_comments)

        if not new_comments:
            logger.info(
                "comment_triage: project=%s chapter=%s no new comments, skip",
                project_id, chapter_id,
            )
            return outcome

        # 2. 拉待处理评论组 (status=new) 供 chief 去重
        pending_q = select(ReviewCommentGroup).where(
            ReviewCommentGroup.project_id == project_id,
            ReviewCommentGroup.status.in_(("new", "discussing")),
        ).order_by(ReviewCommentGroup.created_at.desc()).limit(20)
        pending_groups = (await db.execute(pending_q)).scalars().all()

        # 3. 拉最近主 Agent reply (避免重复) — 最近 20 条
        recent_replies_q = (
            select(ReviewComment)
            .where(
                ReviewComment.project_id == project_id,
                ReviewComment.author_type == "chief_agent",
            )
            .order_by(ReviewComment.created_at.desc())
            .limit(20)
        )
        recent_replies = (await db.execute(recent_replies_q)).scalars().all()

        # 4. 构造 inputs
        inputs = {
            "new_comments_json": json.dumps(
                [_comment_to_triage_input(c) for c in new_comments],
                ensure_ascii=False, indent=2,
            ),
            "pending_groups_json": json.dumps(
                [_group_to_pending_input(g) for g in pending_groups],
                ensure_ascii=False, indent=2,
            ),
            "recent_replies_json": json.dumps(
                [_reply_to_history(r) for r in recent_replies],
                ensure_ascii=False, indent=2,
            ),
        }

        # 5. 调 chief_comment_moderator
        try:
            result = await self.runner.run(
                db,
                agent_key=CHIEF_COMMENT_MODERATOR_KEY,
                template_key=TRIAGE_TEMPLATE_KEY,
                project_id=project_id,
                run_type="comment_triage",
                inputs=inputs,
                response_format="json_object",
            )
            outcome.triage_result = result
        except Exception as exc:
            logger.exception("chief_comment_moderator triage call failed: %s", exc)
            outcome.error = f"chief_call_failed: {exc}"
            return outcome

        parsed = result.parsed or {}
        triage_list = parsed.get("triage") or []
        if not isinstance(triage_list, list):
            logger.warning(
                "comment_triage: parsed.triage is not a list (got %s), skip",
                type(triage_list).__name__,
            )
            return outcome

        # 6. 拉 ReviewSettings (用于 retention + 阈值)
        settings = (
            await db.execute(
                select(ReviewSettings).where(ReviewSettings.project_id == project_id)
            )
        ).scalar_one_or_none()
        if settings is None:
            settings = ReviewSettings(project_id=project_id)
            db.add(settings)
            await db.flush()
        min_severity_rank = SEVERITY_RANK.get(settings.min_severity_for_discussion, 1)

        # 7. 拉 chief_agent AgentRole (用于 author_label)
        chief_role = (
            await db.execute(
                select(AgentRole).where(AgentRole.key == CHIEF_COMMENT_MODERATOR_KEY)
            )
        ).scalar_one_or_none()
        chief_agent_role_id = chief_role.id if chief_role else None

        # 8. 按 comment_id 建索引, 校验每个 triage item 指向真存在的评论
        new_by_id = {c.id: c for c in new_comments}

        for item in triage_list:
            if not isinstance(item, dict):
                continue
            cid = item.get("comment_id")
            action = item.get("action")
            if not isinstance(cid, int) or action not in VALID_ACTIONS:
                logger.warning(
                    "comment_triage: invalid item %r, skip", item,
                )
                outcome.items.append(TriageItemOutcome(
                    comment_id=cid if isinstance(cid, int) else -1,
                    action=str(action),
                    success=False,
                    detail="invalid item",
                    error="bad shape",
                ))
                outcome.error_count += 1
                continue
            comment = new_by_id.get(cid)
            if comment is None:
                # comment_id 不在 new 里 (可能已被处理, 或 chief 幻觉)
                outcome.items.append(TriageItemOutcome(
                    comment_id=cid, action=action, success=False,
                    detail="comment not in pending set",
                    error="not_found",
                ))
                outcome.error_count += 1
                continue

            try:
                if action == ACTION_REPLY:
                    item_out = await self._do_reply(
                        db, comment, item, chief_agent_role_id, settings,
                    )
                    outcome.reply_count += 1
                elif action == ACTION_GROUP:
                    item_out = await self._do_group(
                        db, comment, item, settings,
                    )
                    outcome.group_count += 1
                elif action == ACTION_DISCUSS:
                    item_out = await self._do_discuss(
                        db, comment, item, settings,
                        min_severity_rank=min_severity_rank,
                    )
                    outcome.discuss_count += 1
                else:  # ignore
                    item_out = await self._do_ignore(db, comment, item)
                    outcome.ignore_count += 1
                outcome.items.append(item_out)
            except Exception as exc:
                logger.exception(
                    "comment_triage: item %s action=%s failed: %s",
                    cid, action, exc,
                )
                outcome.items.append(TriageItemOutcome(
                    comment_id=cid, action=action, success=False,
                    detail="exception", error=str(exc),
                ))
                outcome.error_count += 1

        logger.info(
            "comment_triage: project=%s chapter=%s new=%s reply=%s "
            "group=%s discuss=%s ignore=%s err=%s",
            project_id, chapter_id, outcome.new_comment_count,
            outcome.reply_count, outcome.group_count,
            outcome.discuss_count, outcome.ignore_count,
            outcome.error_count,
        )
        return outcome

    # ----- 4 个 action handler -----

    async def _do_reply(
        self,
        db: AsyncSession,
        comment: ReviewComment,
        item: dict[str, Any],
        chief_agent_role_id: int | None,
        settings: ReviewSettings,
    ) -> TriageItemOutcome:
        """action=reply: 写 chief_agent ReviewComment, parent.status='replied'."""
        draft = (item.get("reply_draft") or "").strip()
        if not draft:
            draft = "已收到, 正在评估。"
        reply = ReviewComment(
            project_id=comment.project_id,
            chapter_id=comment.chapter_id,
            chapter_version_id=comment.chapter_version_id,
            parent_id=comment.id,
            target_type=comment.target_type,
            author_type="chief_agent",
            author_label="主 Agent",
            agent_role_id=chief_agent_role_id,
            content=draft[:2000],
            tags=["chief_reply"],
            weight_at_created=1.0,
            status="replied",
            priority=comment.priority,
            expires_at=datetime.utcnow() + timedelta(days=settings.retention_days),
        )
        db.add(reply)
        await db.flush()
        if comment.status == "new":
            comment.status = "replied"
        return TriageItemOutcome(
            comment_id=comment.id, action=ACTION_REPLY, success=True,
            detail=f"reply_id={reply.id}",
        )

    async def _do_group(
        self,
        db: AsyncSession,
        comment: ReviewComment,
        item: dict[str, Any],
        settings: ReviewSettings,
    ) -> TriageItemOutcome:
        """action=group: 加入已有 group 或新建 group, comment.status='grouped'."""
        target_group_id = item.get("target_group_id")
        group: ReviewCommentGroup | None = None
        if isinstance(target_group_id, int):
            group = await db.get(ReviewCommentGroup, target_group_id)
        if group is None:
            # 新建 group
            group = ReviewCommentGroup(
                project_id=comment.project_id,
                chapter_id=comment.chapter_id,
                chapter_version_id=comment.chapter_version_id,
                title=(item.get("reason") or "主 Agent 合并评论")[:200],
                summary=f"自动合并自评论 #{comment.id}",
                comment_ids=[comment.id],
                severity="medium",
                status="new",
            )
            db.add(group)
            await db.flush()
        else:
            # 加入已有 group
            ids = list(group.comment_ids or [])
            if comment.id not in ids:
                ids.append(comment.id)
                group.comment_ids = ids
        comment.related_group_id = group.id
        comment.status = "grouped"
        return TriageItemOutcome(
            comment_id=comment.id, action=ACTION_GROUP, success=True,
            detail=f"group_id={group.id}",
        )

    async def _do_discuss(
        self,
        db: AsyncSession,
        comment: ReviewComment,
        item: dict[str, Any],
        settings: ReviewSettings,
        *,
        min_severity_rank: int,
    ) -> TriageItemOutcome:
        """action=discuss: 升级成 discussion — 必要时建 group + 调 Bridge.

        severity < 阈值: 只标记为 grouped (降级为评论组, 不真开讨论室)
        severity >= 阈值: 真建 group + 调 DiscussionBridge 触发讨论
        """
        severity_hint = (item.get("severity_hint") or "medium").lower()
        sev_rank = SEVERITY_RANK.get(severity_hint, 1)
        if sev_rank < min_severity_rank:
            # 阈值不达, 降级为普通分组, 不开讨论
            group = ReviewCommentGroup(
                project_id=comment.project_id,
                chapter_id=comment.chapter_id,
                chapter_version_id=comment.chapter_version_id,
                title=(item.get("reason") or "主 Agent 合并评论")[:200],
                summary=(
                    f"严重度={severity_hint} (阈值="
                    f"{settings.min_severity_for_discussion}), "
                    f"暂不转入讨论"
                ),
                comment_ids=[comment.id],
                severity=severity_hint if severity_hint in SEVERITY_RANK else "medium",
                status="new",
            )
            db.add(group)
            await db.flush()
            comment.related_group_id = group.id
            comment.status = "grouped"
            return TriageItemOutcome(
                comment_id=comment.id, action=ACTION_DISCUSS, success=True,
                detail=(
                    f"downgraded_to_group_id={group.id} "
                    f"(severity={severity_hint} < threshold)"
                ),
            )

        # 达阈值: 建 group + 调 bridge 开讨论
        group = ReviewCommentGroup(
            project_id=comment.project_id,
            chapter_id=comment.chapter_id,
            chapter_version_id=comment.chapter_version_id,
            title=(item.get("reason") or "主 Agent 升级到讨论")[:200],
            summary=f"严重度={severity_hint}, 自动转讨论",
            comment_ids=[comment.id],
            severity=severity_hint if severity_hint in SEVERITY_RANK else "medium",
            status="new",
        )
        db.add(group)
        await db.flush()
        comment.related_group_id = group.id
        comment.status = "discussing"

        # 调 DiscussionBridge
        try:
            session = await self.bridge.create_from_group(db, group)
            return TriageItemOutcome(
                comment_id=comment.id, action=ACTION_DISCUSS, success=True,
                detail=f"group_id={group.id} session_id={session.id}",
            )
        except Exception as exc:
            logger.exception(
                "comment_triage: discuss bridge failed for group %s: %s",
                group.id, exc,
            )
            # Bridge 失败不致命, group 保持 status=discussing 等 P4 兜底
            return TriageItemOutcome(
                comment_id=comment.id, action=ACTION_DISCUSS, success=False,
                detail=f"group_id={group.id} bridge_failed",
                error=str(exc),
            )

    async def _do_ignore(
        self,
        db: AsyncSession,
        comment: ReviewComment,
        item: dict[str, Any],
    ) -> TriageItemOutcome:
        """action=ignore: 标记为已处理, 不写主 Agent reply."""
        comment.status = "ignored"
        return TriageItemOutcome(
            comment_id=comment.id, action=ACTION_IGNORE, success=True,
            detail=(item.get("reason") or "")[:200],
        )


# ----- input 序列化 helpers (chief_comment_triage prompt 看的) -----

def _comment_to_triage_input(c: ReviewComment) -> dict[str, Any]:
    return {
        "id": c.id,
        "author_type": c.author_type,
        "author_label": c.author_label,
        "content": (c.content or "")[:1000],
        "tags": list(c.tags or []),
        "rating": c.rating,
        "evidence": c.evidence,
        "weight_at_created": c.weight_at_created,
        "priority": c.priority,
        "created_at": c.created_at.isoformat() if c.created_at else None,
    }


def _group_to_pending_input(g: ReviewCommentGroup) -> dict[str, Any]:
    return {
        "id": g.id,
        "title": g.title,
        "summary": g.summary,
        "comment_ids": list(g.comment_ids or []),
        "severity": g.severity,
        "status": g.status,
        "discussion_session_id": g.discussion_session_id,
    }


def _reply_to_history(r: ReviewComment) -> dict[str, Any]:
    return {
        "id": r.id,
        "parent_id": r.parent_id,
        "content": (r.content or "")[:200],
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


# ----- 单例 -----

_service_singleton: CommentTriageService | None = None


def get_comment_triage_service() -> CommentTriageService:
    global _service_singleton
    if _service_singleton is None:
        _service_singleton = CommentTriageService()
    return _service_singleton
