"""WeightService: 读者权重浮动 (P6 §4.5).

规则:
  - 决策 = accepted  → weight += 0.08, adopted_count += 1
  - 决策 = rejected  → weight -= 0.03, rejected_count += 1
  - clamp [0.5, 2.5]
  - 用户评论 (author_type='user') 永远 weight=1.0, 不进浮动

调用时机 (P3 实现):
  - CommentTriageService 把 reader_agent 评论 group 后, 主 Agent 讨论
    完出 decision (accept/reject), 反向调用 WeightService.bump
  - 同一 group 内的每条 reader_agent comment 各自独立 bump
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import not_found
from app.models.comment_review import (
    ReaderAgentProfile,
    ReviewComment,
)

logger = logging.getLogger(__name__)


WEIGHT_MIN = 0.5
WEIGHT_MAX = 2.5
BUMP_ACCEPTED = 0.08
BUMP_REJECTED = 0.03


@dataclass
class WeightBumpResult:
    profile_id: int
    reader_key: str
    old_weight: float
    new_weight: float
    decision: str  # accepted / rejected / skipped
    reason: str  # 调试 / 日志


class WeightService:
    async def bump_for_comment(
        self,
        db: AsyncSession,
        *,
        comment_id: int,
        decision: str,
    ) -> WeightBumpResult | None:
        """对单条 comment 结算权重.

        Returns None 表示该 comment 不参与权重 (user 评论 / 找不到 /
        无效决策), caller 据此忽略。
        """
        decision = (decision or "").lower()
        if decision not in ("accepted", "rejected"):
            return WeightBumpResult(
                profile_id=0, reader_key="", old_weight=0.0, new_weight=0.0,
                decision="skipped", reason=f"invalid decision '{decision}'",
            )
        comment = await db.get(ReviewComment, comment_id)
        if comment is None:
            raise not_found("ReviewComment", str(comment_id))
        if comment.author_type != "reader_agent":
            # 用户评论 + chief_agent 回复 + system 都不进浮动
            return WeightBumpResult(
                profile_id=0, reader_key=comment.author_label,
                old_weight=0.0, new_weight=0.0,
                decision="skipped", reason=f"author_type={comment.author_type}",
            )
        if comment.agent_role_id is None:
            return WeightBumpResult(
                profile_id=0, reader_key=comment.author_label,
                old_weight=0.0, new_weight=0.0,
                decision="skipped", reason="no agent_role_id",
            )
        profile = (
            await db.execute(
                select(ReaderAgentProfile).where(
                    ReaderAgentProfile.agent_role_id == comment.agent_role_id
                )
            )
        ).scalar_one_or_none()
        if profile is None:
            return WeightBumpResult(
                profile_id=0, reader_key=comment.author_label,
                old_weight=0.0, new_weight=0.0,
                decision="skipped", reason="no ReaderAgentProfile",
            )

        old = float(profile.weight or 1.0)
        if decision == "accepted":
            new = old + BUMP_ACCEPTED
            profile.adopted_count = (profile.adopted_count or 0) + 1
        else:  # rejected
            new = old - BUMP_REJECTED
            profile.rejected_count = (profile.rejected_count or 0) + 1
        new = max(WEIGHT_MIN, min(WEIGHT_MAX, new))
        profile.weight = round(new, 4)
        await db.flush()
        logger.info(
            "weight_service: comment=%s reader=%s %s %.3f→%.3f",
            comment_id, profile.reader_key, decision, old, new,
        )
        return WeightBumpResult(
            profile_id=profile.id,
            reader_key=profile.reader_key,
            old_weight=old,
            new_weight=new,
            decision=decision,
            reason="ok",
        )


_service_singleton: WeightService | None = None


def get_weight_service() -> WeightService:
    global _service_singleton
    if _service_singleton is None:
        _service_singleton = WeightService()
    return _service_singleton
