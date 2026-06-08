"""Redis 客户端单例.

阶段 3.3:
  - 用 redis.asyncio 提供异步连接 (arq 内部用它)
  - 用 redis.Redis 提供同步连接 (给统计接口 / 健康检查用)
  - 不在初始化时强 ping, 避免 PG/Redis 还没就绪就崩
"""
from __future__ import annotations

import logging
import os
from typing import Optional

import redis
import redis.asyncio as aioredis
from arq.connections import ArqRedis, RedisSettings, create_pool

from app.core.config import settings

logger = logging.getLogger(__name__)

_async_pool: Optional[ArqRedis] = None
_sync_client: Optional[redis.Redis] = None


def get_redis_settings() -> RedisSettings:
    """从 settings.redis_url 构造 arq 用的 RedisSettings."""
    return RedisSettings.from_dsn(settings.redis_url)


async def get_async_pool() -> ArqRedis:
    """arq 用的异步连接池, 全局单例."""
    global _async_pool
    if _async_pool is None:
        _async_pool = await create_pool(get_redis_settings())
    return _async_pool


async def close_async_pool() -> None:
    """FastAPI lifespan 关闭时调用."""
    global _async_pool
    if _async_pool is not None:
        try:
            await _async_pool.aclose()
        except Exception:  # pragma: no cover
            pass
        _async_pool = None


def get_sync_redis() -> redis.Redis:
    """同步 redis 客户端, 给 /api/worker/queue-summary 这类读路径用."""
    global _sync_client
    if _sync_client is None:
        _sync_client = redis.Redis.from_url(
            settings.redis_url, decode_responses=True,
        )
    return _sync_client


def close_sync_redis() -> None:
    global _sync_client
    if _sync_client is not None:
        try:
            _sync_client.close()
        except Exception:  # pragma: no cover
            pass
        _sync_client = None


async def ping() -> bool:
    """给 /health 与 runtime_worker 心跳用的轻量探测."""
    if not os.environ.get("REDIS_URL") and not settings.redis_url:
        return False
    try:
        client = aioredis.from_url(settings.redis_url, decode_responses=True)
        ok = bool(await client.ping())
        await client.aclose()
        return ok
    except Exception as exc:
        logger.warning("redis ping failed: %s", exc)
        return False
