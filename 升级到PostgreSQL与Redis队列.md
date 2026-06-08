# 升级到 PostgreSQL + Redis 队列 —— 详细 Plan

> 范围：彻底替换 SQLite + 进程内 Worker 轮询，解决“拆书上传 / 写小说启动”反复被 `database is locked` 与“API 主进程被后台长任务拖死”这两个根因。

---

## 1. 升级目标

1. **数据层**：业务库从 SQLite 切到 PostgreSQL，支持高并发写、MVCC、行级锁、JSONB。
2. **任务层**：用 Redis 作为任务队列（`arq` / `Redis Streams`），把 Worker 改成独立服务，API 只入队不执行。
3. **拆书 DeepStudy**：从“单进程跑 1167 章节”改成可水平扩展的“任务网格”。
4. **写小说**：从“API 里直接 await Worker”改成“API 写库 + Redis 入队 + Worker 进程消费”。
5. **可观测**：API / Worker 拆日志、拆状态、拆健康检查。

---

## 2. 架构总览（升级后）

```
┌───────────────┐         ┌──────────────┐
│  Frontend     │  HTTPS  │  FastAPI     │
│  (Vite 5173)  │ ───────▶│  (port 8000) │ ──只做入队 + 读模型──────┐
└───────────────┘         └──────┬───────┘                                │
                                 │                                        │
                                 ▼                                        ▼
                          ┌──────────────┐                       ┌──────────────┐
                          │  Redis       │ ◀── BLPOP / XREAD ── │  Worker      │
                          │  - task:*    │                       │  - writing   │
                          │  - dlq:*     │                       │  - deepstudy │
                          └──────────────┘                       │  - memory    │
                                 ▲                               │  - review   │
                                 │                               │  - discussion│
                                 │                               └──────┬───────┘
                                 │                                      │
                          ┌──────┴───────┐                               │
                          │  PostgreSQL  │ ◀────────读写持久化───────────┘
                          │  (业务数据)  │
                          └──────────────┘
```

要点：

- API 不再 `await get_worker().start()`，也不再 HTTP 自调 `/api/worker/start`。
- Worker 进程作为独立容器/服务启动，从 Redis 拉任务。
- DeepStudy 与写小说走同一套队列，状态写回 PostgreSQL。

---

## 3. 阶段拆分（可逐周验收）

### 阶段 3.1 基础设施（1-2 天）

#### 3.1.1 依赖与编排

新增依赖（写入 `backend/pyproject.toml`）：

```toml
"sqlalchemy[asyncio]>=2.0.30",
"asyncpg>=0.29.0",
"alembic>=1.13.0",
"arq>=0.25.0",
"redis>=5.0.0",
"psycopg2-binary>=2.9.0",
```

新增文件：

- `backend/.env.example`：补 `DATABASE_URL=postgresql+asyncpg://...`、`REDIS_URL=redis://...`
- `backend/alembic.ini`
- `backend/alembic/env.py`
- `backend/alembic/versions/0001_init.py`（baseline migration）

#### 3.1.2 docker-compose 升级

替换 `docker-compose.yml`：

```yaml
services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: novelforge
      POSTGRES_USER: novelforge
      POSTGRES_PASSWORD: novelforge
    volumes:
      - pg_data:/var/lib/postgresql/data
    ports: ["5432:5432"]
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U novelforge"]
      interval: 5s
      timeout: 3s
      retries: 10

  redis:
    image: redis:7-alpine
    command: ["redis-server", "--appendonly", "yes"]
    volumes:
      - redis_data:/data
    ports: ["6379:6379"]
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 10

  backend-api:
    build: .
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000
    environment:
      DATABASE_URL: postgresql+asyncpg://novelforge:novelforge@postgres:5432/novelforge
      REDIS_URL: redis://redis:6379/0
    depends_on:
      postgres: { condition: service_healthy }
      redis: { condition: service_healthy }
    ports: ["8000:8000"]

  backend-worker:
    build: .
    command: python -m app.workers.arq_worker
    environment:
      DATABASE_URL: postgresql+asyncpg://novelforge:novelforge@postgres:5432/novelforge
      REDIS_URL: redis://redis:6379/0
    depends_on:
      postgres: { condition: service_healthy }
      redis: { condition: service_healthy }

  frontend:
    # 保持现有
    depends_on:
      - backend-api

volumes:
  pg_data:
  redis_data:
```

#### 3.1.3 配置层

`backend/app/core/config.py` 调整：

```python
database_url: str = "postgresql+asyncpg://novelforge:novelforge@127.0.0.1:5432/novelforge"
redis_url: str = "redis://127.0.0.1:6379/0"
worker_concurrency: int = 4
worker_max_jobs: int = 8
task_default_ttl_seconds: int = 3600
task_max_retries: int = 3
```

---

### 阶段 3.2 数据库迁移到 PostgreSQL（2-3 天）

#### 3.2.1 SQLAlchemy 改造

`backend/app/core/database.py` 改造点：

- 移除所有 `PRAGMA` 监听器（仅 SQLite 才有）。
- engine 连接参数改为 `pool_size=10, max_overflow=20, pool_pre_ping=True`。
- 增加 `init_db()` → 改为 `run_migrations()`，只允许 Alembic。

`backend/app/core/database.py`（关键片段示意）：

```python
engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    future=True,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
    pool_recycle=1800,
)
```

#### 3.2.2 JSON 列

`backend/app/core/database.py` 已经有 `JSON` 字段。在 PostgreSQL 上 SQLAlchemy 默认映射为 `JSONB`，已能直接承载 study_progress、agent_plan、extra 等大字段。

不需要额外修改模型；只需在迁移里确认列类型：

```python
sa.Column("agent_plan", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
```

#### 3.2.3 Alembic baseline

由于当前是 `Base.metadata.create_all` + 手写 `ensure_column` 列表，迁移路线：

1. 用 `Base.metadata.create_all` 在新的 PostgreSQL 库上生成一次 schema。
2. 用 `alembic revision --autogenerate -m "baseline"` 产出第一个迁移文件。
3. 把 `init_db()` 中手写的 `_COLUMN_BACKFILLS` 全部转成 `alembic/versions` 中的标准升级步骤。
4. 旧 SQLite 库另存为 `data/novelforge.sqlite.backup`，不再写入。

#### 3.2.4 索引与约束补强

迁移文件里显式补：

```sql
CREATE INDEX ix_agent_tasks_pending_pick
  ON agent_tasks (status, task_type, priority DESC, id)
  WHERE status = 'pending';

CREATE INDEX ix_agent_tasks_lease
  ON agent_tasks (lease_expires_at)
  WHERE status = 'running';

CREATE INDEX ix_study_runs_status
  ON study_runs (material_id, status);
```

说明：升级到 Redis 队列后，这些索引主要用于历史查询、运维查 stale 任务、统计接口。

---

### 阶段 3.3 引入 Redis 队列（3-5 天）

推荐使用 **arq**（基于 asyncio、Redis 驱动、FastAPI 生态最自然）。如需更复杂特性可改 Redis Streams。

#### 3.3.1 队列抽象层

新增 `backend/app/queue/__init__.py`、`backend/app/queue/enqueue.py`：

```python
import json
import uuid
from datetime import datetime, timezone

import redis.asyncio as redis
from arq import create_pool
from arq.connections import RedisSettings, ArqRedis

from app.core.config import settings

_redis_pool: ArqRedis | None = None

async def get_redis() -> ArqRedis:
    global _redis_pool
    if _redis_pool is None:
        _redis_pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    return _redis_pool

async def enqueue_task(
    *,
    task_type: str,
    task_id: int,
    domain: str = "writing",
    priority: int = 100,
    delay_seconds: float = 0,
) -> str:
    job_id = f"{task_type}:{task_id}:{uuid.uuid4().hex[:8]}"
    payload = {
        "task_id": task_id,
        "task_type": task_type,
        "enqueued_at": datetime.now(timezone.utc).isoformat(),
    }
    pool = await get_redis()
    await pool.enqueue_job(
        "run_agent_task",
        task_id=task_id,
        task_type=task_type,
        _job_id=job_id,
        _queue=f"q:{domain}",
        _defer_by=delay_seconds,
    )
    return job_id
```

#### 3.3.2 队列拓扑

| Domain       | Redis Key (Stream/List) | 用途 |
|--------------|--------------------------|------|
| writing      | `q:writing`              | 章节流水线 / 启动创作 / 改写 |
| deepstudy    | `q:deepstudy`            | DeepStudy 子任务 |
| review       | `q:review`               | 读者评审 |
| discussion   | `q:discussion`           | 评论区讨论 |
| memory       | `q:memory`               | 记忆整合 |
| model        | `q:model`                | 健康检查 |

每个 domain 一个队列，便于按域调并发。

#### 3.3.3 Worker 改造

新增 `backend/app/workers/arq_worker.py`：

```python
from arq.connections import RedisSettings
from arq.worker import Worker

from app.core.config import settings
from app.workers.handlers import HANDLERS

class NovelForgeWorkerSettings:
    functions = HANDLERS
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    max_jobs = settings.worker_max_jobs
    job_timeout = 3600
    keep_result = 3600
    queue_read_limit = 16
```

启动命令：

```bash
arq app.workers.arq_worker.WorkerSettings
```

#### 3.3.4 任务处理器

新增 `backend/app/workers/handlers.py`：

- `run_agent_task(ctx, task_id: int, task_type: str)`：从 PostgreSQL 拉 `AgentTask`、写 lease、调用原有 `_run_*` 业务函数、更新状态。
- 各 domain handler 复用现有业务：

| 队列任务 | 原代码入口 | 新位置 |
|---|---|---|
| chapter_pipeline | `WorkerController._run_chapter_pipeline` | `handlers.run_chapter_pipeline` |
| project_bootstrap | `WorkerController._run_project_bootstrap` | `handlers.run_project_bootstrap` |
| reader_review | `_run_reader_review` | `handlers.run_reader_review` |
| comment_triage | `_run_comment_triage` | `handlers.run_comment_triage` |
| comment_discussion | `_run_comment_discussion` | `handlers.run_comment_discussion` |
| comment_cleanup | `_run_comment_cleanup` | `handlers.run_comment_cleanup` |
| rewrite_from_discussion | `_run_rewrite_from_discussion` | `handlers.run_rewrite_from_discussion` |
| deepstudy_chunk | `DeepStudyService` | `handlers.run_deepstudy_chunk` |

实现原则：只搬“业务执行”，领取 / 释放 lease / 失败重试全部交给 arq + PostgreSQL 状态。

---

### 阶段 3.4 拆书 DeepStudy 任务网格化（2-3 天）

当前 DeepStudy 是“单进程内 for 章节循环”。改造目标：每章 / 每 stage 一个 arq job。

#### 3.4.1 切分策略

`StudyRun` 已存在，逻辑改为：

```text
Upload / from-text
   └─ 写 StudyRun (status=queued)
        └─ arq: enqueue run_deepstudy_stage(run_id, stage="extract_characters")
             └─ handler 跑完 -> enqueue run_deepstudy_stage(stage="extract_behaviors")
                  └─ ... 直到所有 stage 完成
                       └─ run.status = completed
```

#### 3.4.2 状态落库

handler 启动时：

```sql
UPDATE study_runs SET status='running', current_stage=$1, updated_at=now() WHERE id=$2;
UPDATE study_chapters SET status='processing', started_at=now() WHERE id=$3;
```

handler 成功：

```sql
UPDATE study_runs SET processed_chapters = processed_chapters + 1 WHERE id=$1;
UPDATE study_chapters SET status='done', finished_at=now() WHERE id=$2;
```

handler 失败：

```sql
UPDATE study_chapters SET status='failed', error=$1 WHERE id=$2;
INSERT INTO agent_events (event_type, level, message, ...) VALUES ('deepstudy.chapter_failed', 'error', $1, ...);
```

#### 3.4.3 批处理与并发

- arq `max_jobs=8`，按 material 分组。
- 单本书每 stage 完成后立即写库，不再持有长事务。
- 失败可重试，重试次数由 `task_max_retries` 控制。

#### 3.4.4 拆书 API 行为

`POST /api/study/materials/from-text` 流程调整为：

1. 保存 `StudyMaterial`（status=`uploaded`）。
2. 创建 `StudyRun`。
3. arq 入队 `run_deepstudy_stage(run_id, "ingest")`。
4. **API 不再调用 `get_worker().start()`**。
5. 直接返回 `{"ok": true, "data": {..., "run_id": X}}`。

---

### 阶段 3.5 写小说启动改造（1-2 天）

#### 3.5.1 启动入口

`backend/app/routers/projects.py::launch_project` 改造：

- 删除 `httpx` 自调 `/api/worker/start` 的代码。
- `ProjectLaunchService.launch_semi_auto()` 仍然创建 `Chapter` + `AgentTask`，但任务入 arq：

```python
from app.queue.enqueue import enqueue_task

async def enqueue_first_chapter_task(task_id: int) -> None:
    await enqueue_task(
        task_type="chapter_pipeline",
        task_id=task_id,
        domain="writing",
    )
```

`launch_full_auto()` 创建 `project_bootstrap` 后同样 arq 入队。

#### 3.5.2 章节排队

`ChapterPipeline` 跑完一章后，把下一章也入队。这样写小说可以一章接一章滚下去。

#### 3.5.3 前端无感升级

- 前端调用 `launchProject` 后只看 `first_task_id` 和状态查询。
- `GET /api/projects/{id}/workspace` 返回任务进度时增加 `pending / running / completed` 计数。
- 任务中心 `/api/agent-tasks` 已有，按 `status` 过滤即可。

---

### 阶段 3.6 API 与 Worker 边界清理（1-2 天）

#### 3.6.1 移除 API 内启动 Worker 的逻辑

需要改的位置（已通过排查确认）：

- `backend/app/routers/study.py::_chapterize_and_queue_deepstudy` 中 `await get_worker().start()` 段。
- `backend/app/routers/projects.py::launch_project` 中 `httpx post /api/worker/start` 段。
- 其它直接调 `get_worker().start()` 的地方（需全文扫描）。

#### 3.6.2 保留兼容端点

- `GET /api/worker/status` 保留。
- `GET /api/worker/multi-status` 改为从 Redis 读队列深度 + 读 PostgreSQL 读 worker_status。
- `POST /api/worker/{start,pause,resume,stop,recover}` 改为发到 Redis 的 `control:worker` channel，Worker 进程订阅执行。
- `GET /api/worker/queue-summary` 新增：

```json
{
  "writing": {"pending": 0, "running": 1, "failed": 0, "delayed": 0},
  "deepstudy": {"pending": 0, "running": 0, "failed": 0, "delayed": 0}
}
```

#### 3.6.3 失败恢复

- arq 自带 `on_job_max_retries` 钩子，写入 PostgreSQL `agent_tasks.status='failed'`。
- `recover_stale_tasks` 改造：扫描 `lease_expires_at < now() AND status='running'`，重新入队（不是直接重置 status，因为 Redis 才是真源）。
- DLQ：失败的 job 写入 `dlq:{domain}`，提供 `/api/worker/dlq?domain=writing` 查看。

---

### 阶段 3.7 测试与验收（2-3 天）

#### 3.7.1 后端测试

新增或补充：

- `test_database_postgres.py`：确认 engine 在 PostgreSQL 上启动、JSONB 列可用。
- `test_arq_enqueue.py`：模拟 `enqueue_task`，验证 Redis 出现对应 job。
- `test_arq_handler_chapter_pipeline.py`：handler 直接调用业务函数，验证状态机正确。
- `test_study_upload_no_worker.py`：上传书籍后不启动 Worker 也能 200，run 状态为 `queued`。
- `test_project_launch_no_worker.py`：启动创作后不调 `/api/worker/start`，任务落到队列。
- `test_deepstudy_chunk_concurrency.py`：模拟 100 章节，验证 Redis 中出现对应 job，run 进度递增。
- `test_stale_task_recover.py`：模拟 lease 过期后任务被 Redis 重新投递。
- `test_database_lock_no_more.py`：在 PostgreSQL 下并发写入不出现 `database is locked`（连续 200 次写入）。

#### 3.7.2 手工验收

按你的两个原始问题逐项验证：

**拆书上传**

- [ ] 粘贴正文上传
- [ ] 批量文件上传
- [ ] 上传后不立即启动 worker
- [ ] run 状态从 `queued → running → completed`
- [ ] 上传期间其他 API（写小说、删除）不被卡住
- [ ] 大书（>1000 章）可以水平扩展

**写小说**

- [ ] 半自动启动：outline / character / bible 各自入队
- [ ] 全自动启动：bootstrap 任务入队，LLM 生成大纲 → 创建第一章
- [ ] 任务在 Redis 队列里，Worker 进程消费
- [ ] 失败任务自动重试，最终入 DLQ
- [ ] 停掉 Worker 进程，任务持久化在 Redis / PostgreSQL，重启后继续跑
- [ ] API 启动 / Worker 启动顺序无关（API 先起来也可）

**可观测**

- [ ] API 日志写到 `data/logs/api.log`
- [ ] Worker 日志写到 `data/logs/worker.log`
- [ ] `/api/worker/queue-summary` 返回实时数字
- [ ] `/api/worker/dlq` 可查询失败任务
- [ ] PostgreSQL `pg_stat_activity` 中无长事务

---

## 4. 数据迁移策略

为不丢现有数据，采用双轨过渡：

### 4.1 数据导出

新增一次性脚本 `backend/scripts/migrate_sqlite_to_pg.py`：

- 用 `aiosqlite` 读 `data/novelforge.db`。
- 用 `asyncpg` / SQLAlchemy bulk insert 写入 PostgreSQL。
- 顺序：先 projects，再 user 相关表，再 book / chapter / outline / bible，再 study / memory / events。
- 大表（`study_chapters`、`agent_steps`）分批 `COPY` / `executemany` 1000 行一次。

### 4.2 验证

- 比对两边行数。
- 抽样校验关键表（projects、study_materials、agent_tasks、chapters）。
- 跑一次 `pytest -k smoke`，确保 API 在新数据库上能查询到原有数据。

### 4.3 切换

- 维护期把 `.env` 切到 PostgreSQL，停止旧 API，导入数据，启动新 API。
- 保留旧 SQLite 至少 7 天再删。

---

## 5. 关键风险与回滚

| 风险 | 缓解 | 回滚 |
|------|------|------|
| arq 任务丢失 | 任务执行前先在 PostgreSQL 写 `pending`，handler 写 `running` + `lease`，崩溃后可恢复 | 切回 SQLite + 进程内 Worker |
| DeepStudy 网格化后行为不一致 | 复用 `DeepStudyService` 业务函数，只改驱动；新增 e2e 测试 | 切回单进程实现 |
| PostgreSQL 启动失败 | compose healthcheck + 启动脚本检查 | 回退到 SQLite |
| 前端 / API 协议变化 | 保持所有现有端点 URL / 响应体不变 | 关闭新 API |
| 数据迁移丢数据 | 迁移前全量 SQLite 备份；迁移后行数对比 + 抽样校验 | 用备份还原 SQLite |

---

## 6. 时间估算

| 阶段 | 工作 | 估计 |
|------|------|------|
| 3.1 基础设施 | 依赖 / compose / config | 1-2 天 |
| 3.2 PostgreSQL 迁移 | Alembic + engine 改造 | 2-3 天 |
| 3.3 Redis 队列 | enqueue + arq worker | 3-5 天 |
| 3.4 DeepStudy 网格化 | handler + 状态落库 | 2-3 天 |
| 3.5 写小说改造 | launch + 任务串联 | 1-2 天 |
| 3.6 API 边界清理 | 移除内部 worker 启动 | 1-2 天 |
| 3.7 测试验收 | 自动 + 手工 | 2-3 天 |
| 数据迁移 | 脚本 + 验证 | 1 天 |
| **合计** | | **13-21 天** |

---

## 7. 验收硬指标

升级完成必须满足：

1. **不再出现 `database is locked`**，连续 200 次并发写测试零错误。
2. **API 进程不再启动 Worker**：`backend/app/routers/*.py` 中无 `get_worker().start()` 引用。
3. **Worker 独立服务**：`docker compose up` 同时拉起 `backend-api` 与 `backend-worker` 两个服务。
4. **拆书可扩展**：同一 `StudyRun` 在并发 4 Worker 时吞吐量至少比单进程高 2 倍。
5. **写小说可重试**：连续 5 次手动 kill -9 Worker，未完成任务在重启后全部恢复。
6. **DLQ 可观测**：故意制造 3 次 LLM 超时，任务出现在 `/api/worker/dlq?domain=writing`。
7. **数据可迁移**：`scripts/migrate_sqlite_to_pg.py` 在 5 分钟内完成 4 库数据迁移，行数 100% 对得上。
8. **测试全绿**：`pytest` 在 PostgreSQL + Redis 测试环境全绿。

---

## 8. 建议的落地顺序

1. 先把 `docker-compose.yml` + Postgres + Redis 拉起来，原代码不改动也能跑（只是 DDL 不一致，要让 model 同步一次）。
2. 把 `init_db` + `_COLUMN_BACKFILLS` 换成 Alembic 一次 baseline。
3. 写一个最小 arq worker，验证 hello world 任务可执行。
4. 把现有 `WorkerController._tick` 的“领取任务”逻辑替换为 arq 消费。
5. 业务 handler 逐个迁移。
6. 拆书 DeepStudy 改网格化。
7. 写小说启动改队列。
8. 跑全套测试 + 数据迁移脚本。
9. 端到端手工验收两个原始问题。

这个顺序保证“任何一步出问题，回滚代价小”，符合“直接升级到 Redis + PostgreSQL、不做中间态”的目标，同时避免一次性大改。

---

## 9. 给你的下一步建议

- **如果你 OK 这个 Plan，我可以下周开始阶段 3.1（搭 PG + Redis compose）**。
- **如果你想看更具体的 handler 代码草案**，我可以先写 `backend/app/queue/enqueue.py` 和 `backend/app/workers/arq_worker.py` 雏形给你过目。
- **如果你想保留现有 SQLite 跑回归**（如跑测试套件），我可以在 `conftest.py` 里为 pytest 单独连 SQLite，CI 走 PG，主环境走 PG。这样你不会因为升级被“卡在跑测试”上。

你希望先动哪一块？
