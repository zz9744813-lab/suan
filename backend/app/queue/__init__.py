"""Redis 队列包 — 阶段 3.3 引入.

职责:
  - redis_client.py    Redis 连接池 (同步 redis-py + 异步 redis.asyncio)
  - enqueue.py         业务侧入队 API (供 routers / services 调用)
  - schemas.py         任务体协议 (dataclass, 不绑定 arq, 方便单测)
"""
