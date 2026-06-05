# NovelForge 2.0 P0 Failover + 自动工厂 整合执行计划

> 基于 `P0_Model_Failover_返工技术方案.md` + `NF2_unified_auto_factory_refactor_plan.md`  
> 代码审查日期: 2026-06-05  
> 当前分支: main → 建议切 `fix/p0-model-failover-complete`

---

## 0. 代码审查摘要

### 已存在的基础设施（不需要重写）

| 模块 | 文件 | 状态 |
|------|------|------|
| 模型选择器 | `model_selector.py` (478行) | 已实现，但有 fallback 评分 bug |
| 熔断器 | `model_circuit_breaker.py` (246行) | 已实现 |
| 调用记录器 | `model_call_recorder.py` (224行) | 已实现 |
| 错误分类器 | `error_classifier.py` (47行) | 已实现 |
| Provider 健康 | `provider_health.py` (154行) | 已实现，但与路由探针不统一 |
| Agent 角色模型 | `agent_role.py` (5表) | 已实现，含全部字段 |
| Provider 模型 | `model_provider.py` | 已实现，含全部20+字段 |
| 文体映射 | `genre_prompt_map.py` (2表) | 已实现，含 P11 扩展字段 |
| Worker 健康循环 | `worker.py` L255-276 | 已实现，每300秒 |
| 前端 PageTopbar | `PageTopbar.tsx` | 已实现 |
| 数据库回填 | `database.py` L69-197 | 已实现，含7个表的列回填 |

### 已确认的缺陷

| 编号 | 缺陷 | 严重度 | 文件 | 行号 |
|------|------|--------|------|------|
| BUG-1 | `_prepare_payload()` 无条件注入 JSON 系统提示到所有调用 | 🔴 P0 | `llm/client.py` | L652-679 |
| BUG-2 | fallback 候选固定 `score=0.1`，永远排最后 | 🔴 P0 | `model_selector.py` | L431 |
| BUG-3 | router fallback 只试一次，没有多候选链 | 🟡 P1 | `llm/router.py` | L234-320 |
| BUG-4 | fallback 不排除刚失败的 provider/model | 🟡 P1 | `llm/router.py` | L260-261 |
| BUG-5 | provider_health 和 models 路由探针两套逻辑不统一 | 🟡 P1 | 两个文件 | - |
| BUG-6 | Worker `_tick()` 不检查 `not_before_at`，无延迟重试 | 🔴 P0 | `worker.py` | L296-303 |
| GAP-7 | `AgentRunRecorder` 服务不存在 | 🟡 P1 | 新文件 | - |
| GAP-8 | `model_observability` 路由不存在 | 🟡 P1 | 新文件 | - |
| GAP-9 | 前端模型配置面板功能不完整 | 🟡 P1 | `ModelsPage.tsx` | - |
| GAP-10 | `PromptAutoBinder` 服务/模型/路由不存在 | 🟡 P2 | 新文件 | - |
| GAP-11 | 读者 Agent 编辑中心不存在 | 🟡 P2 | 新页面 | - |
| GAP-12 | 评论评审页仍是手动按钮驱动 | 🟡 P2 | `ReviewCommentsPage.tsx` | - |
| GAP-13 | Prompt 矩阵前端硬编码 Agent 行 | 🟡 P2 | `GenrePromptMatrixPage.tsx` | - |

---

## 1. 执行架构

```
┌─────────────────────────────────────────────────────────────┐
│  Sprint 1: 核心 Bug 修复 (P0 阻断项)                           │
│  ├─ S1-T1: 基线测试 + 分支创建                                │
│  ├─ S1-T2: 修复 JSON 污染 (BUG-1)                             │
│  ├─ S1-T3: 修复 Worker 延迟重试 (BUG-6)                        │
│  └─ S1-T4: 修复 fallback 评分 (BUG-2)                         │
├─────────────────────────────────────────────────────────────┤
│  Sprint 2: Fallback 链 + 健康统一                             │
│  ├─ S2-T1: 多候选 fallback 链 (BUG-3, BUG-4)                  │
│  ├─ S2-T2: 统一 Provider 健康探针 (BUG-5)                      │
│  └─ S2-T3: AgentRun 录制器 (GAP-7)                            │
├─────────────────────────────────────────────────────────────┤
│  Sprint 3: 后端 API 补齐 + 前端模型 UI                         │
│  ├─ S3-T1: Model observability API (GAP-8)                   │
│  ├─ S3-T2: 前端模型绑定编辑面板 (GAP-9)                        │
│  └─ S3-T3: Failover 时间线 + 健康详情弹窗                      │
├─────────────────────────────────────────────────────────────┤
│  Sprint 4: 自动化基础设施                                      │
│  ├─ S4-T1: PromptAutoBinder 后端 (GAP-10)                     │
│  ├─ S4-T2: Prompt 矩阵自动化前端 (GAP-13)                      │
│  └─ S4-T3: 读者 Agent 编辑中心 (GAP-11)                        │
├─────────────────────────────────────────────────────────────┤
│  Sprint 5: 评论全自动 + 审计                                   │
│  ├─ S5-T1: 评论评审自动流 (GAP-12)                             │
│  ├─ S5-T2: 自动化审计中心                                      │
│  └─ S5-T3: Seed 补齐 + 导航整理                               │
├─────────────────────────────────────────────────────────────┤
│  Sprint 6: 测试 + 验收                                        │
│  ├─ S6-T1: 后端专项测试                                        │
│  ├─ S6-T2: 前端构建验证                                        │
│  └─ S6-T3: 端到端功能验收                                      │
└─────────────────────────────────────────────────────────────┘
```

---

## 2. Sprint 1: 核心 Bug 修复

### S1-T1: 基线测试 + 分支创建

**操作:**
```bash
git checkout main && git pull
git checkout -b fix/p0-model-failover-complete
cd backend && python -m pytest -q 2>&1 | tee ../docs/验收记录/P0_FAILOVER_BASELINE.txt
cd ../frontend && npm run build 2>&1 | tee ../docs/验收记录/P0_FAILOVER_BASELINE_FRONTEND.txt
```

**交付:**
- `docs/验收记录/P0_FAILOVER_BASELINE.txt`
- `docs/验收记录/P0_FAILOVER_BASELINE_FRONTEND.txt`

### S1-T2: 修复 LLMClient JSON 污染

**问题:** `_prepare_payload()` 无条件注入 JSON 系统提示 + 在最后用户消息追加 `[系统提醒] 只输出一个 JSON 对象`

**修改文件:**
- `backend/app/services/llm/client.py`

**改动点:**
1. `_prepare_payload()` 新增 `strict_json: bool` 参数
2. 根据 `strict_json` 选择注入内容:
   - `True` → 严格 JSON 系统提示 + 用户消息提醒
   - `False` → 轻量 "不要输出思考过程" 提示
3. `_do_chat()` 和 `_do_chat_stream()` 传递 `strict_json=request.response_format is not None`

**验收:**
- Drafter/Rewriter 调用时不出现 JSON 提示
- Planner/Critic/Continuity 调用时仍强制 JSON
- 新增 `tests/test_llm_client_prompt_mode.py`

### S1-T3: Worker 延迟重试

**问题:** `AgentTask` 有 `retry_count`/`max_retries` 但 `_tick()` 不用；缺 `not_before_at` 字段

**修改文件:**
- `backend/app/models/task.py` — 新增 `not_before_at`, `last_failure_type`, `last_fallback_summary` 字段
- `backend/app/core/database.py` — SQLite 回填三个新列
- `backend/app/workers/worker.py` — `_tick()` 查询加 `not_before_at` 过滤; `_run_chapter_pipeline()` 失败时延迟重试

**改动逻辑:**
```python
# _tick() 查询改为:
AgentTask.status == "pending",
or_(AgentTask.not_before_at.is_(None), AgentTask.not_before_at <= datetime.utcnow())

# 失败处理:
if transient and task.retry_count < task.max_retries:
    task.retry_count += 1
    task.not_before_at = datetime.utcnow() + timedelta(minutes=min(30, 2**task.retry_count))
    task.status = "pending"
    ws.consecutive_failures 不增加
else:
    task.status = "failed"
    ws.consecutive_failures += 1
```

### S1-T4: 修复 fallback 候选评分

**问题:** `_score_all_candidates()` 中 fallback 候选固定 `score=0.1`

**修改文件:**
- `backend/app/services/model_selector.py`

**改动:**
- Fallback 候选参与正常评分流程（capability/health/success/latency/cost/json），不再固定 0.1
- 当 `force_fallback=True` 时，fallback 池优先于普通候选池
- 新增 `exclude: list[tuple[int, str]]` 参数，排除已失败的 provider/model
- 熔断中且 `circuit_open_until > now` 的 Provider 自动跳过

---

## 3. Sprint 2: Fallback 链 + 健康统一

### S2-T1: 多候选 fallback 链

**问题:** 当前 fallback 只试一次，不排除已失败 provider/model

**修改文件:**
- `backend/app/services/llm/router.py`
- `backend/app/services/model_selector.py`

**改动:**
1. `chat()` 中主模型失败后，循环 `MAX_FALLBACK_ATTEMPTS`(2) 次
2. 每次调用 `select_for_agent(force_fallback=True, exclude=attempted)`
3. `attempted` 列表跟踪所有已尝试的 `(provider_id, model_name)`
4. `ModelCallEvent` 新增 `attempt_no`, `fallback_of_event_id`, `fallback_chain_id`
5. `_score_all_candidates()` 过滤 `exclude` 中的 provider/model

### S2-T2: 统一 Provider 健康探针

**问题:** `provider_health.py` 和 `models.py` 路由中各有一套探针

**修改文件:**
- `backend/app/services/provider_health.py`
- `backend/app/routers/models.py`

**改动:**
1. `ProviderHealthService` 支持 `mode="lightweight"` 和 `mode="full"`
2. lightweight: `/models` + short ping (Worker 每5分钟用)
3. full: `/models` + short_chat + json_output + critic_schema + long_text + streaming + recommended_roles (用户手动触发)
4. 统一返回 schema: `ProviderHealthFullResponse`
5. 路由 `/health-check` 改为调用 `ProviderHealthService.check_provider(mode="full")`
6. 写入 `provider.last_health_full` 为结构化 JSON

### S2-T3: AgentRun 录制器

**问题:** `AgentRun`/`AgentRunEvent` 表存在但 Worker 不写

**修改/新增文件:**
- `backend/app/services/agent_run_recorder.py` (新增)
- `backend/app/agents/base.py` (接入)
- `backend/app/services/llm/router.py` (关联 ModelCallEvent)

**改动:**
1. `AgentRunRecorder` 服务: `start_run()`, `event()`, `finish_success()`, `finish_failed()`
2. `BaseAgent.run()` 中创建 AgentRun + 记录事件 (queued/started/llm_request/llm_response/parsed/succeeded/failed/retry/fallback)
3. `ModelCallEvent` 新增 `agent_run_id` 字段关联
4. `router.chat()` 的 `extra` 参数传入 `agent_run_id`

---

## 4. Sprint 3: 后端 API 补齐 + 前端模型 UI

### S3-T1: Model Observability API

**新增文件:**
- `backend/app/routers/model_observability.py`
- `backend/app/main.py` (注册路由)

**端点:**
```
GET /api/model-call-events?agent_role_key=&provider_id=&task_id=&limit=100
GET /api/model-runtime-stats?agent_role_key=&provider_id=&window=rolling_24h
```

### S3-T2: 前端模型绑定编辑面板

**修改/新增文件:**
- `frontend/src/pages/ModelsPage.tsx`
- `frontend/src/components/models/AgentRunDetailPanel.tsx`
- `frontend/src/components/models/AgentBindingModeSwitch.tsx` (新增)
- `frontend/src/components/models/AutoStrategySelect.tsx` (新增)
- `frontend/src/components/models/CandidateProviderPicker.tsx` (新增)
- `frontend/src/components/models/CandidateModelPoolEditor.tsx` (新增)
- `frontend/src/components/models/FallbackCandidateEditor.tsx` (新增)
- `frontend/src/components/models/ModelSelectionPreviewPanel.tsx` (新增)

**功能:**
- 绑定模式切换 (自动/手动/手动+备用)
- 策略选择 (质量优先/成本优先/速度优先/长上下文/JSON稳定)
- 候选 Provider 池多选
- 候选模型池编辑器
- Fallback 候选池
- 预览选择面板 (显示评分原因、候选排序、风险)
- 一键自动配置按钮
- Provider 熔断状态标记 (CircuitBreakerBadge)

### S3-T3: Failover 时间线 + 健康详情弹窗

**新增文件:**
- `frontend/src/components/models/ModelFailoverTimeline.tsx`
- `frontend/src/components/models/ProviderHealthFullModal.tsx`
- `frontend/src/components/models/CircuitBreakerBadge.tsx`

**前端 API 补齐 (`api/index.ts`):**
```ts
previewAgentModelSelection()
autoConfigureAgents()
resetProviderCircuit()
fullProviderHealth()
listModelCallEvents()
```

---

## 5. Sprint 4: 自动化基础设施

### S4-T1: PromptAutoBinder 后端

**新增文件:**
- `backend/app/models/prompt_auto_fill.py` — `PromptAutoFillBatch` + `PromptRecommendationLog` + `PromptTemplatePerformance`
- `backend/app/services/prompt_auto_binder.py` — `PromptAutoBinder` 服务
- `backend/app/routers/prompt_matrix.py` — 矩阵 API 路由
- `backend/app/core/database.py` — 新增表的列回填

**API 端点:**
```
GET    /api/prompts/matrix — 返回完整矩阵（Agent行来自DB，不硬编码）
POST   /api/prompts/matrix/auto-fill/preview
POST   /api/prompts/matrix/auto-fill/apply
POST   /api/prompts/matrix/auto-fill/{batch_key}/rollback
GET    /api/prompts/matrix/cells/{agent_role_key}/{genre}/recommendations
PUT    /api/prompts/matrix/cells/{agent_role_key}/{genre}/lock
PUT    /api/prompts/matrix/cells/{agent_role_key}/{genre}/unlock
GET    /api/prompts/matrix/coverage
GET    /api/prompts/templates/{id}/performance
```

**推荐评分公式:**
```
score = agent_role_match * 0.30 + genre_match * 0.25 + template_tag_match * 0.15
      + historical_quality * 0.15 + output_schema_match * 0.08
      + version_stability * 0.05 + user_pin_bonus * 0.02 - conflict_penalty
```

**硬规则:**
- Drafter 不允许 strict_json 模板
- Critic/MemoryUpdate 优先有 output_schema 的模板
- 读者 Agent 优先对应维度标签
- locked_by_user=true 不覆盖
- score < 0.70 不自动应用；0.70-0.84 仅建议；>= 0.85 自动应用

**现有 GenrePromptMapping 字段已含:** `source`, `confidence_score`, `auto_bind_reason`, `locked_by_user`, `auto_fill_batch_id`, `last_effect_score`, `last_used_at` — 无需新增字段，可直接使用。

### S4-T2: Prompt 矩阵前端自动化

**修改/新增文件:**
- `frontend/src/pages/GenrePromptMatrixPage.tsx` (重构)
- `frontend/src/components/prompts/PromptMatrixTable.tsx` (新增)
- `frontend/src/components/prompts/PromptCell.tsx` (新增)
- `frontend/src/components/prompts/PromptAutoFillPanel.tsx` (新增)
- `frontend/src/components/prompts/PromptRecommendationDrawer.tsx` (新增)
- `frontend/src/components/prompts/PromptCoverageBar.tsx` (新增)
- `frontend/src/components/prompts/PromptBatchHistory.tsx` (新增)

**改造:**
- 删除硬编码 `AGENT_ROWS` 和 `GENRE_LIST`
- Agent 行从 `GET /api/prompts/matrix` 动态获取
- 按分组显示: 写作/读者评审/主Agent讨论/记忆/拆书
- 单元格显示: 模板名 + 匹配度 + 来源 (手动/自动/锁定/建议替换)
- 顶部操作: 预览自动填充/应用高置信/只补空白/回滚/覆盖率

### S4-T3: 5 读者 Agent 编辑中心

**新增文件:**
- `frontend/src/pages/ReaderAgentsPage.tsx`
- `frontend/src/pages/ReaderAgentDetailPage.tsx`
- `frontend/src/App.tsx` (新增路由)

**后端 API:**
```
GET    /api/reviews/readers
GET    /api/reviews/readers/{reader_key}
PATCH  /api/reviews/readers/{reader_key}
GET    /api/reviews/readers/{reader_key}/comments
GET    /api/reviews/readers/{reader_key}/stats
POST   /api/reviews/readers/{reader_key}/test
PUT    /api/reviews/readers/{reader_key}/prompt-binding
PUT    /api/reviews/readers/{reader_key}/model-binding
```

**页面结构:** 左侧读者卡片列表 (钩子/情绪/逻辑/商业/毒点)，右侧选中读者详情 (Prompt/模型/权重/最近评论/统计)

---

## 6. Sprint 5: 评论全自动 + 审计

### S5-T1: 评论评审全自动流

**修改文件:**
- `frontend/src/pages/ReviewCommentsPage.tsx` (重构为三栏自动流视图)
- `backend/app/services/review/reader_review_service.py` (确认 reader_review 后自动入队 triage)
- `backend/app/workers/worker.py` (修复 `rewrite_from_discussion`)

**新增组件:**
- `frontend/src/components/reviews/ReviewAutoFlowPanel.tsx`
- `frontend/src/components/reviews/ReviewCommentFeed.tsx`
- `frontend/src/components/reviews/ReviewGroupPanel.tsx`
- `frontend/src/components/reviews/ReviewDecisionTimeline.tsx`
- `frontend/src/components/reviews/ReviewDebugMenu.tsx`

**自动流程:**
```
chapter_pipeline succeeded
  → enqueue reader_review
  → ReaderReviewService.run_for_chapter()
  → 写入 ReviewComment
  → 自动 enqueue comment_triage (‼️确认已实现)
  → CommentTriageService.run()
  → 高严重度自动 enqueue comment_discussion
  → 需要返工则 enqueue rewrite_from_discussion
  → 返工后自动复评
```

**新增 API:**
```
GET /api/reviews/projects/{project_id}/auto-flow
```

**Bug 修复:**
- `rewrite_from_discussion` 中不读取 `task_row.instruction`，应从 `task_row.payload["rewrite_instruction"]` 或 `ReviewCommentGroup.decision` 中取

### S5-T2: 自动化审计中心

**新增文件:**
- `frontend/src/pages/AutomationAuditPage.tsx`
- 先聚合现有表数据 (AgentRunEvent + ModelCallEvent + PromptRecommendationLog + ReviewComment 等)
- 可选新增 `AutomationAuditEvent` 统一表

**API:**
```
GET /api/audit/events?project_id=&type=&severity=&limit=
GET /api/audit/summary?project_id=
```

**追踪内容:**
- Prompt 自动填充批次
- 模型选择理由
- Provider 熔断与恢复
- 读者评论生成
- 评论合并与裁决
- 返工触发与复评

### S5-T3: Seed 补齐 + 导航整理

**Seed 补充 (`seed.py`):**
- 5 个 reader 的默认 PromptTemplate (reader_hook_comment 等)
- chief_comment_moderator 的 triage/decision PromptTemplate
- discussion participant/synthesis PromptTemplate
- 读者 Agent 的 GenrePromptMapping
- 读者评论输出 schema 标准化

**前端导航 (`App.tsx` + `RailNav.tsx`):**
- 新增路由: `/reader-agents`, `/audit`
- Rail 导航项: 读者、审计
- 各页面统一使用 PageTopbar (已存在)

---

## 7. Sprint 6: 测试 + 验收

### S6-T1: 后端专项测试

**新增测试文件:**
```
backend/app/tests/test_llm_client_prompt_mode.py     (JSON污染测试)
backend/app/tests/test_model_selector_failover.py     (fallback评分测试)
backend/app/tests/test_circuit_breaker.py             (熔断测试)
backend/app/tests/test_llm_router_fallback.py         (多候选fallback测试)
backend/app/tests/test_provider_health_service.py     (健康探针测试)
backend/app/tests/test_worker_retry_delay.py          (延迟重试测试)
backend/app/tests/test_agent_run_recorder.py          (AgentRun录制测试)
backend/app/tests/test_prompt_auto_binder.py          (Prompt自动填充测试)
backend/app/tests/test_prompt_matrix_api.py           (矩阵API测试)
backend/app/tests/test_review_auto_flow.py            (评论自动流测试)
```

**关键测试用例:**

| 测试 | 验证点 |
|------|--------|
| `test_freeform_agent_no_json_prompt` | Drafter调用不含JSON提示 |
| `test_json_agent_strict_prompt` | Critic调用含JSON强制提示 |
| `test_fallback_excludes_failed_model` | fallback不选刚失败的provider/model |
| `test_router_fallback_success_after_timeout` | timeout后fallback成功 |
| `test_circuit_open_provider_skipped` | 熔断Provider被跳过 |
| `test_manual_mode_no_fallback` | 手动模式+不允许fallback时抛错 |
| `test_worker_delays_retry` | 暂时失败进入延迟重试，Worker不停止 |
| `test_auto_fill_high_confidence` | 高置信度模板自动填充 |
| `test_auto_fill_respects_lock` | 锁定格不被覆盖 |
| `test_auto_fill_rollback` | 批次可回滚 |
| `test_chapter_triggers_review` | 章节完成后自动入队评审 |

### S6-T2: 前端构建验证

```bash
cd frontend
npm run build  # 必须无TS错误
npm run test   # 如存在vitest
```

### S6-T3: 端到端功能验收

| 场景 | 验收标准 |
|------|---------|
| A: 自动选模 | Drafter策略改为quality_first，预览显示合适模型+原因 |
| B: 成本优先 | 策略改为cost_first，候选排序变化 |
| C: 主模型失败fallback成功 | 主模型填错model name，fallback成功，时间线显示完整过程 |
| D: 所有Provider失败 | task进入pending retry，Worker不崩溃 |
| E: Drafter正文无JSON污染 | prompt不含"只输出JSON对象"，raw_output是小说正文 |
| F: Prompt自动填充 | 新项目创建后可自动生成矩阵推荐，高置信自动填入 |
| G: 评论自动流 | 章节完成后自动评审，无需手动按钮 |
| H: 读者编辑 | 5个读者可独立编辑Prompt/模型/权重 |

---

## 8. 最终验收清单

```
[ ] Drafter / Rewriter 不再被 JSON 系统提示污染
[ ] Planner / Critic / Continuity / MemoryUpdate 仍强制 JSON
[ ] ModelSelector 能按不同策略给出不同排序
[ ] 主模型失败后能自动 fallback 到备用模型
[ ] fallback 不会选回刚失败的 provider/model
[ ] Provider 熔断后会被自动跳过，并能 half_open 恢复
[ ] Worker 在 Provider 临时失败时不会停止，能延迟重试
[ ] 前端能完整配置模式、策略、候选池、fallback，并能查看事件时间线
[ ] 页面无大页头，首屏直接看到业务内容
[ ] Prompt 矩阵显示所有 Agent（含读者），可自动填充
[ ] 锁定格不被覆盖，可回滚
[ ] 5 读者 Agent 有独立编辑入口
[ ] 章节完成后自动评审，无需手动按钮
[ ] 审计页显示自动化时间线
[ ] 后端 pytest 全部通过
[ ] 前端 npm run build 无错误
[ ] 出现错误的 task 不无限 running
```

---

## 9. 禁止事项

1. 禁止只加字段不接入调用链
2. 禁止用假数据让 UI 显示 running
3. 禁止把所有 Agent 都强制 JSON
4. 禁止 fallback 选回刚失败的 provider/model
5. 禁止 Provider 401 后继续自动重试
6. 禁止 Worker 因单个 Provider 挂掉直接停止
7. 禁止只写前端不补后端测试
8. 禁止删除旧 ModelRoleAssignment 兼容逻辑
9. 禁止把 API Key 返回前端明文
10. 禁止把健康检查做成无限等待，所有探针必须有 timeout
11. 不破坏现有链路: 不删除旧表/旧路由/旧组件
12. 不继续硬编码 Agent 列表/文体列表在前端

---

## 10. 建议提交顺序

```
commit 01: fix: baseline tests + branch setup
commit 02: fix: LLM client strict_json/freeform prompt separation (BUG-1)
commit 03: fix: worker delayed retry with not_before_at (BUG-6)
commit 04: fix: model selector fallback candidate scoring (BUG-2)
commit 05: feat: multi-fallback chain in router (BUG-3, BUG-4)
commit 06: refactor: unify provider health service probes (BUG-5)
commit 07: feat: agent run recorder service (GAP-7)
commit 08: feat: model observability API endpoints (GAP-8)
commit 09: feat: frontend model binding editor + failover timeline (GAP-9)
commit 10: feat: prompt auto binder backend (GAP-10)
commit 11: feat: prompt matrix frontend automation (GAP-13)
commit 12: feat: reader agents editing center (GAP-11)
commit 13: feat: comment review auto-flow UI (GAP-12)
commit 14: feat: automation audit center
commit 15: feat: seed completion + navigation polish
commit 16: test: failover + auto-fill regression tests
commit 17: docs: final acceptance report
```

---

## 11. 耗时预估

| Sprint | 内容 | 预估文件数 |
|--------|------|-----------|
| S1 | 核心Bug修复 (4个task) | 5-8 |
| S2 | Fallback链+健康统一 (3个task) | 6-8 |
| S3 | API+前端模型UI (3个task) | 10-15 |
| S4 | 自动化基础设施 (3个task) | 12-18 |
| S5 | 评论+审计+Seed (3个task) | 8-12 |
| S6 | 测试+验收 (3个task) | 10-15 |

**总计: ~50-76 个文件变更**

---

*计划制定时间: 2026-06-05 12:44 GMT+8*
*基于两个技术方案 + 完整代码审查*
