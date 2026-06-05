"""P9: Discussion Worker — 轮询 pending_discussion 线程并执行讨论。

运行频率：每 20 秒轮询一次。
并行限制：MAX_PARALLEL_DISCUSSIONS = 2
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.discussion_trace import DiscussionThread

logger = logging.getLogger(__name__)

MAX_PARALLEL_DISCUSSIONS = 2


async def discussion_worker_tick() -> int:
    """轮询 pending_discussion / discussing 线程并执行。

    Returns: 处理的线程数
    """
    processed = 0
    async with AsyncSessionLocal() as db:
        # 查看当前正在讨论的数量
        discussing_count = (await db.execute(
            select(DiscussionThread).where(
                DiscussionThread.status == "discussing"
            )
        )).scalars().all()
        slots = max(0, MAX_PARALLEL_DISCUSSIONS - len(discussing_count))

        if slots <= 0:
            return 0

        threads = (await db.execute(
            select(DiscussionThread)
            .where(DiscussionThread.status.in_(["pending_discussion", "failed"]))
            .order_by(
                # critical > high > medium > low
                DiscussionThread.risk_level.desc(),
                DiscussionThread.created_at.asc(),
            )
            .limit(slots)
        )).scalars().all()

    for thread in threads:
        try:
            from app.agents.discussion_orchestrator import DiscussionOrchestrator
            orchestrator = DiscussionOrchestrator()
            async with AsyncSessionLocal() as db:
                await orchestrator.run_thread(db, thread.id)
            processed += 1
        except Exception as exc:
            logger.error(f"Discussion worker error for thread {thread.id}: {exc}")

    return processed
