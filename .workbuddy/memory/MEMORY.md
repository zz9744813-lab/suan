# NovelForge 2.0 — 项目长期记忆

## 项目概况
- 长篇小说 AI 协同写作工作台，Python/FastAPI 后端 + React/TypeScript 前端
- 版本 0.1.0，P0-P10 + P0 Failover返工 + NF2自动工厂 + P0可观测性重构 + P0拆书书架修复 全部完成

## 关键架构
- 后端：FastAPI + SQLAlchemy async + SQLite，`backend/app/` 下 models/routers/services/agents/workers/prompts
- 前端：React 18 + Zustand + Vite
- Agent 基类：`BaseAgent`，`AgentContext(db, task, project_id, chapter_id, project_genre, inputs)`
- Prompt 引擎：`PromptEngine`，`resolve_for_agent(agent_key, genre)` + `render(template_key, inputs)`
- PromptAutoBinder: 按 agent_key 前缀匹配 + genre 关键词评分自动绑定
- 模型 Failover: LLMRouter 多候选 fallback 链(MAX_FALLBACK_ATTEMPTS=2)，CircuitBreaker 三态熔断
- 延迟重试: Worker 指数退避(30s×2^n, max 300s)，`not_before_at` 排除
- 可观测性: ModelCallEvent 30+字段(event_type/category/level/summary/fallback), 8个API端点, 10个前端组件
- ORM: `tags_json`→`tags`, `source_payload_json`→`source_payload`(property映射)
- FK: AgentTask表名=`agent_tasks`; Worker `task_row.instruction`不存在,用`payload.get("rewrite_instruction")`
- ShelfLayout: title可选prop,标题区条件渲染
- session_scope()自动commit,路由不要手动commit

## 拆书书架 P0 修复 (2026-06-06)
- 入口: `/study` → 重定向 `/study/library`，旧页保留在 `/study/upload`
- 加书: AddBookModal (文件上传+粘贴正文)，后端 `POST /materials/from-text` 一站式
- 删除: `StudyDeleteService` 深度清理16张衍生产物表，`POST /materials/batch-delete` 批量
- 分类: 书架从状态分组改为分类优先 (SHELF_CATEGORIES)，`isTestBook()` 自动识别
- 诊断: `GET /deepstudy/materials/{id}/diagnostics` 8种空图原因分析
- `StudyMaterialUpdate` 已支持 `shelf_category` + `extra`

## 用户偏好
- 文件不要保存到 C 盘
- 项目路径：`F:\kelaode\Data\Agents\zhongji8633\wudi8633\`
