# NovelForge 2.0 — 项目长期记忆

## 项目概况
- 长篇小说 AI 协同写作工作台，Python/FastAPI 后端 + React/TypeScript 前端
- 8 个核心 Agent：Planner / Drafter / Critic / Rewriter / Continuity / MemoryUpdater / Learner / Study
- 版本 0.1.0，P0-P5 迭代完成，P6 评论区评审系统完成，P7 Prompt 类型矩阵进行中

## 关键架构
- 后端：FastAPI + SQLAlchemy async + SQLite，`backend/app/` 下 models/routers/services/agents/workers/prompts
- 前端：React 18 + Zustand + Vite，@dnd-kit 已安装
- Agent 基类：`BaseAgent`，`AgentContext(db, task, project_id, chapter_id, project_genre, inputs)`
- Prompt 引擎：`PromptEngine`，支持 `resolve_for_agent(agent_key, genre)` 和传统 `render(template_key, inputs)`

## 用户偏好
- 文件不要保存到 C 盘
- 项目路径：`F:\kelaode\Data\Agents\zhongji8633\wudi8633\`
