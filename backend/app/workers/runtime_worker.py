"""runtime_worker — 阶段 3.1 占位 Worker 进程入口.

目的: 让 docker-compose 的 ``backend-worker`` 服务能起一个常驻进程,
保证 PG/Redis 启动后 5 个服务都健康.

本阶段不做实际任务消费, 仅:
  1. 校验环境变量 (DATABASE_URL / REDIS_URL)
  2. ping PostgreSQL 与 Redis
  3. 周期性打印心跳到 stdout (挂载到 docker logs)
  4. 优雅处理 SIGTERM / SIGINT

阶段 3.3 会在此模块挂上真正的 arq Worker class.
阶段 3.2 会在此模块加 PG/Redis 启动 wait.
"""
from __future__ import annotations

import asyncio
import logging
import os
import signal
import sys
from datetime import datetime, timezone

logger = logging.getLogger("novelforge.runtime_worker")


async def _ping_postgres() -> bool:
    try:
        from sqlalchemy import text
        from app.core.database import engine
        async with engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception as exc:
        logger.warning("postgres ping failed: %s", exc)
        return False


async def _ping_redis() -> bool:
    try:
        import redis.asyncio as aioredis
        from app.core.config import settings
        client = aioredis.from_url(settings.redis_url, decode_responses=True)
        pong = await client.ping()
        await client.aclose()
        return bool(pong)
    except Exception as exc:
        logger.warning("redis ping failed: %s", exc)
        return False


async def _heartbeat_loop(stop_event: asyncio.Event) -> None:
    while not stop_event.is_set():
        ts = datetime.now(timezone.utc).isoformat()
        pg_ok = await _ping_postgres()
        redis_ok = await _ping_redis()
        logger.info(
            "heartbeat ts=%s postgres=%s redis=%s pid=%s",
            ts, pg_ok, redis_ok, os.getpid(),
        )
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=15.0)
        except asyncio.TimeoutError:
            continue


async def _main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    logger.info("runtime_worker starting pid=%s", os.getpid())
    logger.info("DATABASE_URL=%s", os.environ.get("DATABASE_URL", "<unset>"))
    logger.info("REDIS_URL=%s", os.environ.get("REDIS_URL", "<unset>"))

    stop_event = asyncio.Event()

    def _on_signal(signame: str) -> None:
        logger.info("received %s, shutting down", signame)
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, _on_signal, sig.name)
        except NotImplementedError:
            # Windows / 某些受限环境不支持 add_signal_handler
            pass

    try:
        await _heartbeat_loop(stop_event)
    finally:
        logger.info("runtime_worker exited pid=%s", os.getpid())

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))
