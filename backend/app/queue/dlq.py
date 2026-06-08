"""DLQ (Dead Letter Queue) 写入 — 阶段 3.3 引入.

把 arq 走到 on_job_max_retries 的任务体落到 Redis 列表 ``dlq:{domain}``,
``/api/worker/dlq`` 接口读这个列表.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from app.core.config import settings
from app.queue.enqueue import domain_for_task_type
from app.queue.redis_client import get_sync_redis

DLQ_KEY_TEMPLATE = "dlq:{domain}"
DLQ_MAX_LEN = 1000


async def write_dlq(*, job_id: str, task_id: int, task_type: str, error: str) -> None:
    domain = domain_for_task_type(task_type)
    key = DLQ_KEY_TEMPLATE.format(domain=domain)
    payload = {
        "job_id": job_id,
        "task_id": task_id,
        "task_type": task_type,
        "domain": domain,
        "error": error,
        "failed_at": datetime.now(timezone.utc).isoformat(),
    }
    # DLQ 写入走同步客户端足够 (小数据, 不在乎 await)
    client = get_sync_redis()
    pipe = client.pipeline()
    pipe.lpush(key, json.dumps(payload, ensure_ascii=False))
    pipe.ltrim(key, 0, DLQ_MAX_LEN - 1)
    pipe.execute()


def list_dlq(domain: str = "writing", limit: int = 50) -> list[dict[str, Any]]:
    client = get_sync_redis()
    rows = client.lrange(DLQ_KEY_TEMPLATE.format(domain=domain), 0, max(0, limit - 1))
    out: list[dict[str, Any]] = []
    for raw in rows:
        try:
            out.append(json.loads(raw))
        except Exception:  # pragma: no cover
            out.append({"raw": raw})
    return out


def queue_depth(domain: str) -> dict[str, int]:
    """给 /api/worker/queue-summary 用: pending + running.

    arq 没有暴露单独的 pending 队列深度, 这里用 in-progress 列表长度近似.
    """
    from arq.jobs import Job

    from app.queue.redis_client import get_async_pool
    return _queue_depth_sync(domain)


def _queue_depth_sync(domain: str) -> dict[str, int]:
    """同步读, 不依赖 event loop. 用 redis client 直接 stat 队列 key."""
    import redis as _redis
    client = _redis.Redis.from_url(settings.redis_url, decode_responses=True)
    queue_key = f"arq:queue:{domain}"
    in_progress_key = f"arq:in-progress:{domain}"
    result_key = f"arq:result:{domain}"
    try:
        pending = int(client.llen(queue_key) or 0)
        running = int(client.scard(in_progress_key) or 0)
        result = int(client.zcard(result_key) or 0)
    finally:
        client.close()
    return {"pending": pending, "running": running, "result": result}
