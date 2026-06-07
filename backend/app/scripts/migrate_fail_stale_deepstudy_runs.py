"""清理卡死的 deepstudy_run。

只标 failed + error, 不删行 (保留 audit)。

匹配条件:
- task_type == 'deepstudy_run'
- status == 'running'  (状态机卡死)
- started_at IS NULL    (worker 从没接手过)
- 或 started_at < now - 2h (worker 接手但无进度, 极少见)

其他状态 (pending / succeeded / failed / cancelled) 保留。
"""
import asyncio
import logging
from datetime import datetime, timedelta

from sqlalchemy import update

from app.core.database import session_scope
from app.models.task import AgentTask

logging.disable(logging.CRITICAL)


async def main() -> None:
    two_hours_ago = datetime.utcnow() - timedelta(hours=2)
    async with session_scope() as db:
        # 1. 标 started_at=NULL 的 running 任务
        res1 = await db.execute(
            update(AgentTask)
            .where(
                AgentTask.task_type == "deepstudy_run",
                AgentTask.status == "running",
                AgentTask.started_at.is_(None),
            )
            .values(
                status="failed",
                error="worker 未启动时被卡死, 已被自动清理 (worker 池 workers=0)",
                finished_at=datetime.utcnow(),
            )
        )
        print(f"  [NULL-start] 标 failed: {res1.rowcount} 行")

        # 2. 标超时 (>2h 无 finished_at 的 running 任务)
        res2 = await db.execute(
            update(AgentTask)
            .where(
                AgentTask.task_type == "deepstudy_run",
                AgentTask.status == "running",
                AgentTask.started_at.is_not(None),
                AgentTask.started_at < two_hours_ago,
                AgentTask.finished_at.is_(None),
            )
            .values(
                status="failed",
                error="拆书任务超时 (>2h 无进度), 已被自动清理",
                finished_at=datetime.utcnow(),
            )
        )
        print(f"  [2h-stale]   标 failed: {res2.rowcount} 行")

        # 3. 兜底: deepstudy_run pending 的, 也加上 created_at 检查 (避免 24h+ 没 worker 接的)
        from app.models.task import AgentTask as A2
        res3 = await db.execute(
            update(A2)
            .where(
                A2.task_type == "deepstudy_run",
                A2.status == "pending",
                A2.created_at < two_hours_ago,
            )
            .values(
                status="failed",
                error="拆书任务在 pending 队列超过 2h, 已被自动清理",
                finished_at=datetime.utcnow(),
            )
        )
        print(f"  [pending>2h] 标 failed: {res3.rowcount} 行")

        total = res1.rowcount + res2.rowcount + res3.rowcount
        print(f"  total cleaned: {total} rows")


if __name__ == "__main__":
    asyncio.run(main())
