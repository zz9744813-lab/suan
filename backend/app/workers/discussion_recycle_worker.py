"""P9: Discussion Recycle Worker — 7 天后回收讨论并沉淀 Skill。

运行频率：每 60 秒轮询一次。
回收策略：
  - 原始 Agent 发言压缩进 archive_payload_json
  - 最终结论永久保留
  - Skill 草案固化 / 拒绝 / 延长观察
"""
from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.discussion_trace import (
    DiscussionMessage,
    DiscussionSkillDraft,
    DiscussionThread,
)
from app.services.discussion_trace import SkillBuilderService

logger = logging.getLogger(__name__)


async def discussion_recycle_tick() -> int:
    """扫描到期线程并回收。

    Returns: 回收的线程数
    """
    recycled = 0
    now = datetime.utcnow()

    async with AsyncSessionLocal() as db:
        # 找到 recycle_at <= now 且未回收的线程
        threads = (await db.execute(
            select(DiscussionThread)
            .where(
                DiscussionThread.recycle_at <= now,
                DiscussionThread.status.notin_(["recycled", "pending_discussion", "discussing"]),
            )
            .order_by(DiscussionThread.recycle_at.asc())
            .limit(10)
        )).scalars().all()

    for thread in threads:
        try:
            await _recycle_thread(thread.id)
            recycled += 1
        except Exception as exc:
            logger.error(f"Recycle worker error for thread {thread.id}: {exc}")

    return recycled


async def _recycle_thread(thread_id: int) -> None:
    """回收单个线程。"""
    async with AsyncSessionLocal() as db:
        thread = await db.get(DiscussionThread, thread_id)
        if not thread or thread.status == "recycled":
            return

        # 压缩消息
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
                    "decision_tags": m.decision_tags_json,
                }
                for m in messages
            ],
            "final_decision": thread.final_decision,
            "final_reason": thread.final_reason,
            "recycled_at": datetime.utcnow().isoformat(),
        }
        thread.archive_payload_json = archive
        thread.recycled_at = datetime.utcnow()
        thread.status = "recycled"
        thread.updated_at = datetime.utcnow()

        # 评估 Skill 草案
        if thread.skill_draft_id:
            draft = await db.get(DiscussionSkillDraft, thread.skill_draft_id)
            if draft and draft.status == "draft":
                # 简单评估：quality_score >= 0.6 则固化
                if draft.quality_score >= 0.6:
                    try:
                        sb = SkillBuilderService()
                        await sb.solidify_skill_draft(db, draft.id)
                    except Exception as exc:
                        logger.warning(f"Auto-solidify skill draft {draft.id} failed: {exc}")
                else:
                    draft.status = "rejected"

        # 删除原始消息
        for m in messages:
            await db.delete(m)

        await db.commit()
