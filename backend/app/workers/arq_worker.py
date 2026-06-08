"""arq Worker 启动入口 — 阶段 3.3.

用 ``arq app.workers.arq_worker.WorkerSettings`` 启动进程.

为什么用单独入口而不是让 API 进程也起 arq:
  - arq 是长期阻塞的 event loop, 不适合塞在 uvicorn 里
  - 阶段 3.1 的 runtime_worker 现在被 arq 取代, 但保留 import 兼容
"""
from __future__ import annotations

import logging
import os

from arq.worker import Function, LoggingSettings, Worker

from app.core.config import settings
from app.queue.redis_client import get_redis_settings
from app.workers.deepstudy_handlers import (
    run_deepstudy_dispatch,
    run_deepstudy_stage,
)
from app.workers.queue_handlers import (
    on_job_max_retries,
    on_shutdown,
    on_startup,
    run_agent_task,
)

logger = logging.getLogger(__name__)


# arq 通过模块级 ``WorkerSettings`` 反射构建 Worker.
# 我们自己 new 一个 Worker, 跟 FastAPI 启动 / 测试解耦, 但又跟
# arq CLI 入口 (WorkerSettings) 行为一致.
def build_worker() -> Worker:
    return Worker(
        functions=[
            Function(run_agent_task, name="run_agent_task"),
            Function(run_deepstudy_dispatch, name="study_deepstudy_dispatch"),
            # stage 任务: 每个 stage_key 都注册到 arq
            Function(
                run_deepstudy_stage,
                name="study_ds_chapter_profile",
            ),
            Function(
                run_deepstudy_stage,
                name="study_ds_entity_extract",
            ),
            Function(
                run_deepstudy_stage,
                name="study_ds_event_extract",
            ),
            Function(
                run_deepstudy_stage,
                name="study_ds_scene_beat_extract",
            ),
            Function(
                run_deepstudy_stage,
                name="study_ds_relationship_analyze",
            ),
            Function(
                run_deepstudy_stage,
                name="study_ds_behavior_pattern_mine",
            ),
            Function(
                run_deepstudy_stage,
                name="study_ds_technique_mine",
            ),
        ],
        on_startup=on_startup,
        on_shutdown=on_shutdown,
        on_job_max_retries=on_job_max_retries,
        redis_settings=get_redis_settings(),
        max_jobs=int(settings.worker_max_jobs),
        job_timeout=3600,
        keep_result=3600,
        queue_read_limit=16,
        health_check_interval=30,
        logging=LoggingSettings(level=logging.INFO),
    )


# 兼容 arq CLI: ``arq app.workers.arq_worker.WorkerSettings``
class WorkerSettings:  # pragma: no cover - exercised only via arq CLI
    functions = [
        Function(run_agent_task, name="run_agent_task"),
        Function(run_deepstudy_dispatch, name="study_deepstudy_dispatch"),
        Function(run_deepstudy_stage, name="study_ds_chapter_profile"),
        Function(run_deepstudy_stage, name="study_ds_entity_extract"),
        Function(run_deepstudy_stage, name="study_ds_event_extract"),
        Function(run_deepstudy_stage, name="study_ds_scene_beat_extract"),
        Function(run_deepstudy_stage, name="study_ds_relationship_analyze"),
        Function(run_deepstudy_stage, name="study_ds_behavior_pattern_mine"),
        Function(run_deepstudy_stage, name="study_ds_technique_mine"),
    ]
    on_startup = on_startup
    on_shutdown = on_shutdown
    on_job_max_retries = on_job_max_retries
    redis_settings = get_redis_settings()
    max_jobs = int(settings.worker_max_jobs)
    job_timeout = 3600
    keep_result = 3600
    queue_read_limit = 16
    health_check_interval = 30


async def amain() -> None:  # pragma: no cover
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    logger.info(
        "arq worker starting redis=%s max_jobs=%s",
        os.environ.get("REDIS_URL", settings.redis_url),
        settings.worker_max_jobs,
    )
    worker = build_worker()
    await worker.async_run()


if __name__ == "__main__":  # pragma: no cover
    import asyncio

    asyncio.run(amain())
