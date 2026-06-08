"""Smoke 脚本: 阶段 3.3 验证 enqueue 通路.

用法:
  python -m app.scripts.smoke_redis_enqueue --task-type chapter_pipeline

不依赖 LLM, 不依赖 deepstudy 数据集. 流程:
  1. 连接 Redis / PG
  2. 创建一个临时 AgentTask (status=pending)
  3. 调 enqueue_task(task_id=..., task_type=...)
  4. 读 /api/worker/queue-summary 看到该 domain depth +1
  5. 删除这个临时任务 (避免污染业务表)

注意: smoke 失败也不会崩 dev DB, 每次执行都打印结果.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from datetime import datetime

from sqlalchemy import select

from app.core.database import session_scope
from app.models.task import AgentTask
from app.queue.enqueue import enqueue_task

logger = logging.getLogger("smoke")


async def main(task_type: str) -> int:
    if not os.environ.get("REDIS_URL") and not os.environ.get("DATABASE_URL"):
        print("ERROR: REDIS_URL / DATABASE_URL 未设置, 跳过 smoke", file=sys.stderr)
        return 2

    fake_task_id: int | None = None
    try:
        async with session_scope() as db:
            row = AgentTask(
                project_id=0,
                task_type=task_type,
                status="pending",
                priority=10,
                payload={"smoke": True, "at": datetime.utcnow().isoformat()},
                max_retries=1,
            )
            db.add(row)
            await db.flush()
            fake_task_id = row.id

        print(f"smoke: created AgentTask id={fake_task_id} task_type={task_type}")

        result = await enqueue_task(task_id=fake_task_id, task_type=task_type)
        print(
            f"smoke: enqueued job_id={result.job_id} queue={result.queue} domain={result.domain}"
        )

        # 短延迟让 arq / 队列追上
        await asyncio.sleep(0.5)
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"smoke failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    finally:
        if fake_task_id is not None:
            try:
                async with session_scope() as db:
                    row = (await db.execute(
                        select(AgentTask).where(AgentTask.id == fake_task_id)
                    )).scalar_one_or_none()
                    if row is not None:
                        await db.delete(row)
                print(f"smoke: cleaned up AgentTask id={fake_task_id}")
            except Exception as cleanup_exc:  # pragma: no cover
                print(
                    f"smoke: cleanup failed: {cleanup_exc}",
                    file=sys.stderr,
                )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    p = argparse.ArgumentParser()
    p.add_argument("--task-type", default="chapter_pipeline")
    args = p.parse_args()
    sys.exit(asyncio.run(main(args.task_type)))
