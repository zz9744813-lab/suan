# NovelForge 2.0 — 项目长期记忆

## 项目概况
- 长篇小说 AI 协同写作工作台，Python/FastAPI 后端 + React/TypeScript 前端
- 8 个核心 Agent：Planner / Drafter / Critic / Rewriter / Continuity / MemoryUpdater / Learner / Study
- 版本 0.1.0，P0-P5 迭代完成，P6 评论区评审系统完成，P7 Prompt 类型矩阵完成，P8 行为模式库完成，P9 讨论室自动留痕完成，P10 Agent 分层记忆池完成

## 关键架构
- 后端：FastAPI + SQLAlchemy async + SQLite，`backend/app/` 下 models/routers/services/agents/workers/prompts
- 前端：React 18 + Zustand + Vite，@dnd-kit 已安装
- Agent 基类：`BaseAgent`，`AgentContext(db, task, project_id, chapter_id, project_genre, inputs)`
- Prompt 引擎：`PromptEngine`，支持 `resolve_for_agent(agent_key, genre)` 和传统 `render(template_key, inputs)`
- 讨论 Worker：主 Worker 的 `_run_forever` 中集成 `_discussion_worker_loop`（20s）和 `_recycle_worker_loop`（60s）
- 旧表兼容：discussion_sessions/turns 保留，新表 discussion_threads/messages/sources/skill_drafts/recycle_jobs/skills 并存
- Agent 记忆池：四层分层（temporary→task→long_term→permanent），6 张新表，`session_scope()` 自动 commit，路由不要手动 commit
- ORM ↔ Schema 字段映射：`tags_json` → `tags`（通过 property），`source_payload_json` → `source_payload`（通过 property），`content_preview`（通过 property）
- FK 约束：AgentTask 表名是 `agent_tasks` 不是 `generation_tasks`

## 用户偏好
- 文件不要保存到 C 盘
- 项目路径：`F:\kelaode\Data\Agents\zhongji8633\wudi8633\`
