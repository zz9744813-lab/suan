# NovelForge 2.0 — 项目长期记忆

## 项目概况
- 长篇小说 AI 协同写作工作台，Python/FastAPI 后端 + React/TypeScript 前端
- 8 个核心 Agent：Planner / Drafter / Critic / Rewriter / Continuity / MemoryUpdater / Learner / Study
- 版本 0.1.0，P0-P10 迭代完成，P0 Model Failover 返工完成，NF2 自动工厂阶段1完成

## 关键架构
- 后端：FastAPI + SQLAlchemy async + SQLite，`backend/app/` 下 models/routers/services/agents/workers/prompts
- 前端：React 18 + Zustand + Vite，@dnd-kit 已安装
- Agent 基类：`BaseAgent`，`AgentContext(db, task, project_id, chapter_id, project_genre, inputs)`
- Prompt 引擎：`PromptEngine`，支持 `resolve_for_agent(agent_key, genre)` 和传统 `render(template_key, inputs)`
- PromptAutoBinder: `services/prompt_auto_binder.py`，按 agent_key 前缀匹配 + genre 关键词评分自动绑定
- 讨论 Worker：主 Worker 的 `_run_forever` 中集成 `_discussion_worker_loop`（20s）和 `_recycle_worker_loop`（60s）
- 旧表兼容：discussion_sessions/turns 保留，新表 discussion_threads/messages/sources/skill_drafts/recycle_jobs/skills 并存
- Agent 记忆池：四层分层（temporary→task→long_term→permanent），6 张新表，`session_scope()` 自动 commit，路由不要手动 commit
- 模型 Failover: LLMRouter 支持多候选 fallback 链(MAX_FALLBACK_ATTEMPTS=2)，CircuitBreaker 三态熔断
- 延迟重试: Worker `_mark_task_failed()` 指数退避(30s×2^n, max 300s)，`not_before_at` 排除
- ORM ↔ Schema 字段映射：`tags_json` → `tags`（通过 property），`source_payload_json` → `source_payload`（通过 property），`content_preview`（通过 property）
- FK 约束：AgentTask 表名是 `agent_tasks` 不是 `generation_tasks`
- Worker bug: `task_row.instruction` 不存在，应从 `task_row.payload.get("rewrite_instruction")` 取

## P0 Model Failover 完成项
- LLMClient: strict_json 分离，Drafter/Rewriter 不再被 JSON 系统提示污染
- ModelSelector: fallback 候选真实评分(非固定0.1)，5 种策略(quality/cost/speed/long_context/json_stable)
- LLMRouter: chat() 多候选 fallback 链，跳过已失败 provider/model
- ProviderHealthService: 轻量探针不覆盖 last_health_full
- Worker: not_before_at 延迟重试 + 指数退避
- 前端: 10 个模型配置组件 + AgentRunDetailPanel 改造 + 可观测性面板 + 审计日志页

## NF2 自动工厂完成项
- PromptAutoFillBatch/PromptRecommendationLog/PromptTemplatePerformance 三张新表
- prompt_matrix router: preview/apply/rollback/recommendations/lock/unlock/coverage/performance
- 读者 Agent 编辑中心: ReaderAgentsPage + ReaderAgentDetailPage + 5 个后端 API
- 评论评审自动化: ReviewAutoFlowPanel + ReviewCommentFeed + ReviewGroupPanel + ReviewDecisionTimeline + ReviewDebugMenu + auto-flow API
- 审计页: AutomationAuditPage
- Prompt 矩阵: 后端驱动(非硬编码) + Section分组(写作/读者/主Agent/记忆/拆书)
- 前端 API: 16 个新函数 + listModelCallEvents
- 后端测试: 8 个专项测试文件

## 用户偏好
- 文件不要保存到 C 盘
- 项目路径：`F:\kelaode\Data\Agents\zhongji8633\wudi8633\`
