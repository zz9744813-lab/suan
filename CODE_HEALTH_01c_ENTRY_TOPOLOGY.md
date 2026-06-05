# 后端入口与 API 拓扑 (Phase 1.3)

## A. 应用入口 `backend/app/main.py`

| 元素 | 内容 |
|------|------|
| 框架 | FastAPI |
| 中间件 | CORS（origins/credentials/methods/headers 全部放开） |
| 异常处理 | 全局 `APIError` 处理器 → `JSONResponse{ok:false, error:{...}}` |
| 启动钩子 | `init_db()` → `seed()` → `event_bus.publish(app.ready)` |
| 关闭钩子 | `get_worker().stop()` |
| 基础端点 | `GET /`、`GET /health` |
| API 前缀 | 由 `settings.api_prefix` 决定（默认 `/api`） |

## B. Router 注册清单（24 个 router，223 个端点）

`main.py` 第 109-120 行通过 `app.include_router(r, prefix=PREFIX)` 批量挂载：

| Router 模块 | 端点数 | 业务域 |
|------------|------:|--------|
| `projects` | 15 | 项目 CRUD |
| `chapters` | 4 | 章节 |
| `tasks` | 8 | 任务调度 |
| `prompts` | 7 | 提示词模板版本管理 |
| `models` | 12 | 模型 Provider/Role/Circuit/Health |
| `worker` | 6 | 后台 worker 控制 |
| `chief_agent` | 5 | 总主编 agent |
| `memory` | 11 | 记忆 |
| `events` | 1 | 事件流 SSE |
| `study` | 21 | 拆书（最大模块） |
| `behavior` | 5 | 行为 |
| `graph` | 10 | 知识图谱 |
| `discussion` | 3 | 群戏讨论 |
| `search` | 1 | 全文检索 |
| `deepstudy` | 10 | 深度研究 |
| `project_memory` | 11 | 项目记忆 |
| `agent_roles` | 10 | Agent 角色矩阵 |
| `agent_roles.agent_runs_router` | (在 agent_roles 中) | Agent 运行 |
| `reviews` | 27 | 读者评论/审阅（最大模块之一） |
| `genre_prompts` | 8 | 类型 Prompt |
| `prompt_matrix` | 8 | Prompt 矩阵 |
| `behavior_card` | 6 | 行为卡 |
| `behavior_card.cat_router` | (在 behavior_card 中) | 行为卡分类 |
| `discussion_trace` | 10 | 讨论追踪 |
| `agent_memory` | 13 | Agent 记忆 |
| `agent_memory.change_router` | (在 agent_memory 中) | 记忆变更 |
| `model_observability` | 8 | 模型可观测性 |
| `audit` | 3 | 审计日志 |
| **合计** | **223** | （按行计数 @router 装饰器） |

> 说明：`agent_roles.agent_runs_router`、`behavior_card.cat_router`、`agent_memory.change_router` 三个子 router 与主 router 在同一文件内定义，共用同一 module 路径。

## C. 调用链：典型请求路径

```
前端 (React) 
    ↓ fetch /api/...
FastAPI 路由 (routers/study.py 等)
    ↓ Depends()
服务层 (services/deepstudy/coordinator.py 等)
    ↓
数据层 (models/* SQLAlchemy ORM)
    ↓
SQLite (aiosqlite)
```

异步并发：
```
主请求 (routers/*) ──┐
                     ├─> 后台 Worker (workers/pipeline.py) ──> LLM Client (services/llm/client.py)
事件总线 (core/events.py) ──> SSE 推送 (routers/events.py)
```

## D. 关键外部依赖

来自 `pyproject.toml`：
- **Web 框架**：fastapi 0.115, uvicorn
- **数据**：sqlalchemy 2.0, aiosqlite
- **校验**：pydantic 2.9
- **HTTP/客户端**：httpx
- **流式响应**：sse-starlette
- **重试**：tenacity
- **文档解析**：pypdf, python-docx, bs4, lxml, ebooklib
- **测试**：pytest 8.3, pytest-asyncio 0.24, ruff 0.7
