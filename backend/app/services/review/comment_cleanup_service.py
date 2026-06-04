"""P6 §4.6 CommentCleanupService — 过期 review_comments 清理.

规则 (P6 spec §4.6):
  1. 删除 review_comments where expires_at < now()
  2. 删除评论前, 采纳统计必须已写入 ReaderAgentProfile (decide_group 阶段完成)
  3. DiscussionSession / DiscussionTurn / ReviewCommentGroup.decision 不删除
  4. 跳过 author_type in (chief_agent, system) — 主 Agent 回复永久保留
  5. 跳过 status='discussing' — 讨论还没结束, 不删原文

触发:
  - P4 §5.5 worker 启动时入队一次 (priority=10, 跑空闲时)
  - P1 端点 POST /api/reviews/cleanup (手动触发, 给管理面板用)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.comment_review import ReviewComment

logger = logging.getLogger(__name__)


# 不删的 author_type (P3 §4.6 第 4 条: chief_agent reply 永久保留)
IMMORTAL_AUTHOR_TYPES: frozenset[str] = frozenset({"chief_agent", "system"})


@dataclass
class CleanupOutcome:
    """CommentCleanupService.cleanup_expired 的结果."""

    scanned: int
    deleted: int
    skipped_immortal: int
    skipped_discussing: int
    retention_days: int
    error: str | None = None


class CommentCleanupService:
    """清理过期 review_comments.

    单测路径 — pytest 不友好 (DB + 时区), P4 阶段只暴露 run() 跟单测
    友好的 in-memory 模拟. 真实验证走 test_p4_e2e.py.
    """

    def __init__(self) -> None:
        pass

    async def cleanup_expired(
        self,
        db: AsyncSession,
        *,
        retention_days: int = 7,
        now: datetime | None = None,
    ) -> CleanupOutcome:
        if retention_days < 1:
            return CleanupOutcome(
                scanned=0, deleted=0,
                skipped_immortal=0, skipped_discussing=0,
                retention_days=retention_days,
                error="retention_days must be >= 1",
            )

        now = now or datetime.utcnow()

        # 0. 全部过期候选 (含 immortal / discussing) — 给 scanned 一个
        # 透明的"全局候选"数, 方便审计
        all_candidates_q = select(ReviewComment).where(
            ReviewComment.expires_at.is_not(None),
            ReviewComment.expires_at < now,
        )
        all_rows = (await db.execute(all_candidates_q)).scalars().all()
        scanned = len(all_rows)

        # 1. 拉候选: 过期 + 非 immortal + 非 discussing
        candidates_q = select(ReviewComment).where(
            ReviewComment.expires_at.is_not(None),
            ReviewComment.expires_at < now,
            ReviewComment.author_type.notin_(IMMORTAL_AUTHOR_TYPES),
            ReviewComment.status != "discussing",
        )
        rows = (await db.execute(candidates_q)).scalars().all()

        # 1.5 统计 SQL 过滤掉的 immortal / discussing (从 all_rows 算)
        # 注意: all_rows 已经过滤 expires_at < now, 这里再看 author_type/status
        all_skipped_immortal = sum(
            1 for c in all_rows if c.author_type in IMMORTAL_AUTHOR_TYPES
        )
        all_skipped_discussing = sum(
            1 for c in all_rows if c.status == "discussing"
        )

        if not rows:
            logger.info(
                "comment_cleanup: now=%s retention=%s scanned=%s nothing to do",
                now.isoformat(), retention_days, scanned,
            )
            return CleanupOutcome(
                scanned=scanned, deleted=0,
                skipped_immortal=all_skipped_immortal,
                skipped_discussing=all_skipped_discussing,
                retention_days=retention_days,
            )

        # 2. 删除 (走 delete + RETURNING 不优雅, 改 ORM 级联)
        # 单独统计 skipped 类型 (虽然 SQL 已经过滤, 但防御性再次校验)
        to_delete: list[int] = []
        for c in rows:
            if c.author_type in IMMORTAL_AUTHOR_TYPES:
                continue  # 已被 SQL 过滤, 防御性
            if c.status == "discussing":
                continue  # 已被 SQL 过滤, 防御性
            if c.expires_at is None or c.expires_at >= now:
                continue  # 防御性
            to_delete.append(c.id)

        if to_delete:
            await db.execute(
                delete(ReviewComment).where(ReviewComment.id.in_(to_delete))
            )
            await db.flush()
            logger.info(
                "comment_cleanup: deleted %d comments (retention=%s scanned=%d)",
                len(to_delete), retention_days, scanned,
            )

        return CleanupOutcome(
            scanned=scanned,
            deleted=len(to_delete),
            skipped_immortal=all_skipped_immortal,
            skipped_discussing=all_skipped_discussing,
            retention_days=retention_days,
        )


_cleanup_singleton: CommentCleanupService | None = None


def get_comment_cleanup_service() -> CommentCleanupService:
    global _cleanup_singleton
    if _cleanup_singleton is None:
        _cleanup_singleton = CommentCleanupService()
    return _cleanup_singleton


__all__ = [
    "CleanupOutcome",
    "CommentCleanupService",
    "get_comment_cleanup_service",
    "IMMORTAL_AUTHOR_TYPES",
]
