# NovelForge 2.0 自进化系统工程实施 Plan

## 0. 文档目标

本文档定义 NovelForge 2.0 的自学习、自评估、自修复、自进化、全天候运行与可训练数据沉淀方案。

交付目标：

- 系统能 24/7 自动运行。
- 每次写作、拆书、评审、讨论都能转化为可追踪学习信号。
- 学习信号能生成可评估、可应用、可回滚的 `EvolutionPatch`。
- 低风险改动自动应用，高风险改动进入人工确认。
- Prompt、记忆、技能卡、模型路由策略能持续迭代。
- 自动沉淀 fine-tune / LoRA 可用训练数据。
- 新增模块必须保持清晰边界，避免继续扩大 `pipeline.py`、`worker.py` 等大文件。

---

## 1. 当前代码接入点

| 域 | 现有文件 | 用途 | 改造方式 |
|---|---|---|---|
| 写作流水线 | `backend/app/workers/pipeline.py` | 章节生产主链路 | 只加事件出口，不继续堆业务逻辑 |
| Agent 调用 | `backend/app/agents/base.py` | 记录 AgentStep / Prompt / LLM 输出 | 保持不动，新增读取层 |
| LearningAgent | `backend/app/agents/learner.py` | 生成学习复盘 | 输出结构化 JSON，作为进化输入 |
| LearningService | `backend/app/services/learning.py` | MVP 统计 | 改为 lightweight analyzer 或废弃合并进 evolution |
| Evolution 模型 | `backend/app/models/evolution.py` | 已有进化表 | 补字段、补 service/router/worker |
| AgentMemory | `backend/app/models/agent_memory.py` | 四层记忆 | 增加收益归因、健康分更新 |
| PromptEngine | `backend/app/services/prompt_engine.py` | Prompt 渲染和路由 | 增加实验版本读取，不直接改核心渲染逻辑 |
| PromptAutoBinder | `backend/app/services/prompt_auto_binder.py` | 自动绑定 Prompt | 接入 `last_effect_score` 自动回填 |
| ModelSelector | `backend/app/services/model_selector.py` | 模型选择 | 接入质量收益统计，不在 selector 内做复杂分析 |
| ModelCallRecorder | `backend/app/services/model_call_recorder.py` | 模型调用统计 | 输出作为质量归因输入 |
| DeepStudy | `backend/app/services/deepstudy/` | 拆书和技巧挖掘 | 修复假完成，输出技能/训练样本 |
| WorkerController | `backend/app/workers/worker.py` | 后台循环 | 只挂载新 worker，不把 evolution 逻辑写进去 |
| 前端路由 | `frontend/src/App.tsx` | 页面入口 | 新增 `/evolution` |
| Dashboard | `frontend/src/pages/Dashboard.tsx` | 总控台 | 新增进化状态卡，不堆复杂列表 |

---

## 2. 总体架构

```txt
ChapterPipeline / DeepStudy / Review / Discussion
        │
        ▼
Observation Collector
        │
        ▼
Evolution Analyzer
        │
        ▼
EvolutionPatch Queue
        │
        ├── Prompt Experiment Evaluator
        ├── Memory Impact Evaluator
        ├── SkillCard Impact Evaluator
        ├── Model Strategy Evaluator
        └── FineTune Dataset Builder
        │
        ▼
Evolution Applier
        │
        ├── Apply low-risk patch
        ├── Request approval for medium-risk patch
        ├── Reject high-risk patch
        └── Rollback failed patch
        │
        ▼
Next Run Uses Updated Prompt / Memory / Skill / Model Strategy
```

核心原则：

- `pipeline.py` 只负责生产章节，不负责进化分析。
- `worker.py` 只负责调度，不承载业务逻辑。
- 每个进化动作必须落库。
- 每个自动改动必须可回滚。
- 所有自动行为必须有审计日志。
- 用户锁定项不可自动覆盖。
- 高风险改动不可自动应用。

---

## 3. 新增后端模块

### 3.1 `backend/app/services/evolution/`

新增目录：

```txt
backend/app/services/evolution/
  __init__.py
  collector.py
  analyzer.py
  patch_service.py
  evaluator.py
  applier.py
  prompt_experiment.py
  memory_impact.py
  skill_impact.py
  model_quality.py
  finetune_dataset.py
  safety.py
  fingerprints.py
```

### 3.2 模块职责

| 文件 | 职责 |
|---|---|
| `collector.py` | 从 AgentStep、ChapterVersion、Critic、ReaderReview、ModelCallEvent 收集观测数据 |
| `analyzer.py` | 归因：失败原因、成功模式、风险因素、候选动作 |
| `patch_service.py` | 创建、查询、去重、状态流转 `EvolutionPatch` |
| `evaluator.py` | 统一评估入口，根据 patch_type 分发 |
| `applier.py` | 应用 patch、写审计、生成 rollback snapshot |
| `prompt_experiment.py` | Prompt 候选版本、历史回放、A/B 评分 |
| `memory_impact.py` | 记忆使用收益统计、升降权、冲突标记 |
| `skill_impact.py` | SkillCard 注入效果、成功率、晋级/降权 |
| `model_quality.py` | 按 Agent 角色聚合模型质量收益 |
| `finetune_dataset.py` | 构建 SFT、rewrite、preference pair 数据集 |
| `safety.py` | 风险等级、预算限制、自动应用策略 |
| `fingerprints.py` | patch 去重、样本去重、Prompt 版本指纹 |

### 3.3 禁止事项

- 禁止在 `pipeline.py` 中直接写 Prompt 修改逻辑。
- 禁止在 `worker.py` 中直接分析失败原因。
- 禁止在 router 中写业务判断。
- 禁止自动覆盖用户锁定配置。
- 禁止没有 rollback snapshot 的自动应用。

---

## 4. 数据库改造

### 4.1 补强 `EvolutionPatch`

当前已有 `EvolutionPatch`，建议增加字段：

```python
scope: str | None                  # global / project / chapter / agent_role
confidence: float                  # 0-1
expected_gain: float | None         # 预期收益
actual_gain: float | None           # 应用后实际收益
rollback_json: dict | None          # 回滚数据
source_signal_ids: list | None      # AgentStep / Review / ModelCallEvent 等来源
fingerprint: str | None             # 去重指纹
auto_apply_policy: str              # never / low_risk_only / always_if_passed
requires_human_review: bool
applied_by: str | None              # system / user / agent
reverted_at: datetime | None
revert_reason: str | None
```

索引：

```txt
ix_evolution_patch_status
ix_evolution_patch_type
ix_evolution_patch_project_status
ix_evolution_patch_fingerprint
```

### 4.2 新增 `EvolutionSignal`

用途：统一记录可学习信号。

```python
class EvolutionSignal(Base):
    __tablename__ = "evolution_signals"

    id: int
    project_id: int | None
    chapter_id: int | None
    task_id: int | None
    source_type: str       # agent_step / critic / reader_review / model_call / deepstudy / user_edit
    source_id: str | None
    signal_type: str       # failure / success / conflict / cost_spike / user_preference / style_pattern
    severity: str          # info / low / medium / high / critical
    payload_json: dict
    confidence: float
    created_at: datetime
```

### 4.3 新增 `PromptExperiment`

```python
class PromptExperiment(Base):
    __tablename__ = "prompt_experiments"

    id: int
    project_id: int | None
    agent_role_key: str
    genre: str | None
    base_template_id: int
    base_version_id: int
    candidate_version_id: int
    status: str            # queued / running / passed / failed / promoted / rejected
    sample_count: int
    score_before: float | None
    score_after: float | None
    cost_usd: float
    evaluation_json: dict | None
    created_at: datetime
    finished_at: datetime | None
```

### 4.4 新增 `TrainingSample`

```python
class TrainingSample(Base):
    __tablename__ = "training_samples"

    id: int
    project_id: int | None
    chapter_id: int | None
    sample_type: str       # sft / rewrite / preference / critic / planner
    quality_score: float
    status: str            # candidate / approved / exported / rejected
    instruction: str
    input_json: dict
    output_text: str | None
    chosen_text: str | None
    rejected_text: str | None
    source_refs: list | None
    fingerprint: str
    created_at: datetime
    exported_at: datetime | None
```

### 4.5 新增 `FineTuneJob`

```python
class FineTuneJob(Base):
    __tablename__ = "fine_tune_jobs"

    id: int
    provider_id: int
    base_model: str
    result_model_name: str | None
    status: str            # queued / uploading / running / succeeded / failed / cancelled
    provider_job_id: str | None
    dataset_path: str | None
    sample_count: int
    metrics_json: dict | None
    error: str | None
    created_at: datetime
    finished_at: datetime | None
```

---

## 5. 状态机设计

### 5.1 EvolutionPatch 状态

```txt
proposed
  ├── duplicate
  ├── rejected
  └── evaluating
        ├── evaluation_failed
        └── evaluation_passed
              ├── pending_human_review
              ├── applied
              └── rejected
applied
  ├── verified
  └── rolled_back
```

### 5.2 自动应用规则

| 风险 | 条件 | 动作 |
|---|---|---|
| low | 评估通过，收益为正，有 rollback | 自动应用 |
| medium | 影响 Prompt active version / 模型策略 | 等待人工确认 |
| high | 永久记忆、全局模型策略、批量删除 | 禁止自动应用 |
| critical | 数据不可逆、无 rollback、跨项目影响 | 只生成报告 |

### 5.3 Patch 去重规则

fingerprint 输入：

```txt
patch_type + target_type + target_id + normalized(after_json) + project_id
```

规则：

- 24 小时内重复 patch 直接标记 `duplicate`。
- 已 applied 的相同 patch 不重复应用。
- rejected patch 7 天内不重新生成，除非 source_signal 新增高严重度证据。

---

## 6. 写作流水线接入

### 6.1 修改点

文件：`backend/app/workers/pipeline.py`

只增加一个出口调用：

```python
await get_evolution_service().on_chapter_pipeline_completed(
    db,
    task=task,
    chapter=chapter,
    result=result_payload,
)
```

要求：

- 调用位置在 `LearningAgent` 完成后、`pipeline.completed` 事件前后均可。
- 不在 `pipeline.py` 中构造 patch。
- `result_payload` 只传基础数据，不传复杂 ORM 对象树。

### 6.2 `result_payload` 字段

```python
{
    "final_score": current_score,
    "pass_score": policy.pass_score,
    "pass_status": pass_status,
    "rewrite_rounds": rewrite_rounds,
    "hard_conflicts": check.hard_conflicts,
    "issues": issues,
    "total_cost_usd": round(total_cost, 4),
    "total_input_tokens": total_in,
    "total_output_tokens": total_out,
    "total_duration_ms": total_dur,
}
```

---

## 7. EvolutionService 详细需求

### 7.1 `on_chapter_pipeline_completed`

输入：

- `task`
- `chapter`
- `result_payload`

流程：

1. 调用 `collector.collect_chapter_run()`。
2. 写入 `EvolutionSignal`。
3. 调用 `analyzer.analyze_chapter_run()`。
4. 生成候选 patch。
5. 调用 `patch_service.create_many_deduped()`。
6. 低风险 patch 入评估队列。
7. 发布 SSE 事件 `evolution.patch_proposed`。

输出：

```python
{
    "signals_created": int,
    "patches_created": int,
    "patches_duplicate": int,
}
```

### 7.2 失败归因规则

必须覆盖以下场景：

| 信号 | 触发条件 | patch 候选 |
|---|---|---|
| 低分 | `final_score < pass_score` | prompt_patch / skill_card_patch |
| 边缘通过 | `pass_score <= final_score < pass_score + 5` | prompt_patch |
| 重写过多 | `rewrite_rounds >= 2` | planner_prompt_patch / drafter_skill_patch |
| 硬冲突 | `hard_conflicts` 非空 | memory_patch / detail_guard_patch |
| 成本异常 | cost 高于最近均值 2 倍 | model_strategy_patch |
| JSON 失败 | ModelCallEvent 有 json_parse_failed | model_strategy_patch / prompt_patch |
| 用户改稿 | 存在 user_edit version | training_sample / preference_sample |
| 读者低评 | reader_score 低 | critic_prompt_patch / skill_card_patch |

### 7.3 成功模式提炼

触发条件：

- `final_score >= pass_score + 8`
- `rewrite_rounds == 0`
- 无 hard conflict
- ReaderReview 平均分高

动作：

- 生成 `skill_card_patch`
- 生成 `training_sample`
- 更新相关 Prompt 的正向效果分
- 更新相关模型质量统计

---

## 8. Prompt 自进化需求

### 8.1 Prompt 候选生成

输入：

- base PromptVersion
- 失败归因
- 最近 5-20 个相关 AgentStep
- 成功样本
- 禁止修改项

输出：

- 新 `PromptVersion(status="candidate")`
- 一条 `EvolutionPatch(patch_type="prompt_patch")`
- 一条 `PromptExperiment(status="queued")`

### 8.2 回放评估

回放样本选择：

- 同 project 优先。
- 同 genre 优先。
- 同 agent_role_key。
- 低分样本和高分样本都要包含。
- MVP 阶段每次最多 3 个样本，后续扩展到 10-20 个。

评估指标：

| 指标 | 权重 |
|---|---:|
| Critic 分数提升 | 40% |
| JSON 解析稳定性 | 20% |
| 重写轮数下降 | 15% |
| 成本变化 | 10% |
| 输出长度合规 | 10% |
| 禁忌违背 | 5% |

晋级条件：

```txt
score_after >= score_before + 3
AND json_failure_rate 不上升
AND cost_delta <= 30%
AND no critical violation
```

### 8.3 应用规则

- candidate version 通过后改为 `active`。
- 旧 active 改为 `archived`。
- 写入 rollback：旧 active version id。
- 用户锁定 mapping 不自动改。
- 每次晋级写 `AuditLog`。

---

## 9. 记忆自净化需求

### 9.1 记忆使用记录

每次 ContextCompiler 或 MemoryRetrievalService 使用记忆时，必须写：

- memory_id
- project_id
- chapter_id
- task_id
- injected_into
- prompt_excerpt
- used_at

已有 `AgentMemoryAccessLog` 可复用。

### 9.2 收益归因

写作结束后，按被使用记忆更新：

```txt
高分 + 无冲突 → health_score +0.03
低分 + hard conflict 相关 → health_score -0.08, is_conflicted=True
长期未使用 → health_score 衰减
用户 pin → 不自动降权
permanent → 不自动修改，只生成 MemoryChangeRequest
```

### 9.3 层级调整

| 条件 | 动作 |
|---|---|
| temporary 被多次使用且正收益 | promote 到 task |
| task 连续正收益 | promote 到 long_term |
| long_term 产生冲突 | 标记 conflicted，生成修复 patch |
| 低 health 且未 pin | archive |
| permanent 冲突 | 生成 change request |

---

## 10. SkillCard 自进化需求

### 10.1 SkillCard 来源

来源包括：

- DeepStudy technique_mine
- behavior_pattern_mine
- 高分章节 LearningAgent 总结
- 讨论室固化技能
- 用户采纳的改稿模式

### 10.2 Skill 注入

新增 `SkillInjector`：

```txt
backend/app/services/evolution/skill_impact.py
```

输入：

- project_id
- genre
- chapter outline
- characters_present
- scene tags
- conflict tags

输出：

```python
[
    {
        "skill_id": 1,
        "title": "冲突升级节奏",
        "prompt_hint": "...",
        "checklist": [...],
        "match_reason": "genre+scene tag matched",
    }
]
```

注入位置：

- Planner：结构类技能
- Drafter：写法类技能
- Critic：检查清单
- Rewriter：修复策略

### 10.3 收益更新

写作后写 `SkillUsageEvent`：

- critic_score_before
- critic_score_after
- reader_score
- rewrite_rounds
- outcome

更新 `SkillCard.success_score`：

```txt
success_score = 0.8 * old + 0.2 * outcome_score
```

晋级：

```txt
usage_count >= 5 AND success_score >= 0.75 → status=active
```

降权：

```txt
usage_count >= 5 AND success_score <= 0.35 → status=deprecated
```

---

## 11. 模型路由自优化需求

### 11.1 质量指标

按 `agent_role_key + provider_id + model_name` 聚合：

- avg_critic_score
- avg_reader_score
- avg_rewrite_rounds
- json_parse_failure_rate
- continuity_issue_count
- avg_latency_ms
- avg_cost_usd
- fallback_success_rate

写入 `ModelQualityStat`。

### 11.2 接入 ModelSelector

`ModelSelectorService` 不直接分析原始数据，只读取聚合结果。

新增评分项：

```txt
quality_gain_score = normalized(ModelQualityStat.avg_critic_score)
stability_score = 1 - json_parse_failure_rate
cost_quality_score = quality_gain_score / max(avg_cost_usd, min_cost)
```

策略：

- quality_first：质量权重高。
- cost_first：性价比权重高。
- balanced：质量、稳定、成本均衡。
- json_strict：JSON 稳定性优先。

### 11.3 锁定规则

- `selection_mode=manual` 不自动改。
- `manual_with_fallback` 只优化 fallback candidates。
- `auto` 可自动调整排序。

---

## 12. Fine-tune / LoRA 数据沉淀需求

### 12.1 样本类型

| sample_type | 来源 | 用途 |
|---|---|---|
| sft | 高分最终章节 | 训练生成能力 |
| rewrite | 初稿 + critic → 终稿 | 训练改写能力 |
| preference | chosen/rejected | DPO / preference tuning |
| critic | 章节 → 结构化评价 | 训练评价能力 |
| planner | 大纲上下文 → chapter plan | 训练规划能力 |

### 12.2 样本入库条件

必须满足：

- 来源可追溯。
- 内容非空。
- fingerprint 不重复。
- quality_score >= 最低阈值。
- 不包含明显错误 JSON。
- 用户标记禁止训练的项目不入库。

### 12.3 导出格式

SFT JSONL：

```json
{"messages":[{"role":"system","content":"..."},{"role":"user","content":"..."},{"role":"assistant","content":"..."}]}
```

Preference JSONL：

```json
{"prompt":"...","chosen":"...","rejected":"..."}
```

### 12.4 FineTune Adapter

新增：

```txt
backend/app/services/finetune/
  __init__.py
  base.py
  openai_compatible.py
  local_lora.py
  dataset_exporter.py
```

接口：

```python
class FineTuneAdapter:
    async def supports(self, provider: ModelProvider) -> bool: ...
    async def upload_dataset(self, dataset_path: str) -> str: ...
    async def create_job(self, base_model: str, dataset_id: str) -> str: ...
    async def get_status(self, job_id: str) -> FineTuneJobStatus: ...
    async def register_model(self, job: FineTuneJob) -> None: ...
```

---

## 13. 全天候 Worker 需求

### 13.1 新增 Worker

```txt
backend/app/workers/evolution_worker.py
backend/app/workers/evaluation_worker.py
backend/app/workers/finetune_worker.py
```

### 13.2 WorkerController 接入

`backend/app/workers/worker.py` 只新增任务启动：

```python
self._evolution_task = asyncio.create_task(...)
self._evaluation_task = asyncio.create_task(...)
self._finetune_task = asyncio.create_task(...)
```

不得把业务逻辑写进 `WorkerController`。

### 13.3 调度频率

| Worker | 频率 | 职责 |
|---|---:|---|
| evolution_worker | 60s | 扫描 signals，生成 patch |
| evaluation_worker | 120s | 评估 queued patch / prompt experiment |
| finetune_worker | 1h | 构建样本、导出数据集、轮询微调 job |
| memory_worker | 60s | 过期清理、健康分衰减 |
| model_worker | 300s | 模型健康检查、质量聚合 |

### 13.4 预算限制

新增配置：

```python
EVOLUTION_DAILY_COST_LIMIT_USD=2.0
EVOLUTION_DAILY_LLM_CALL_LIMIT=200
EVOLUTION_AUTO_APPLY_ENABLED=true
EVOLUTION_HIGH_RISK_REQUIRE_REVIEW=true
FINETUNE_AUTO_SUBMIT=false
```

预算超限：

- 停止评估类 LLM 调用。
- 继续收集 signal。
- 继续生成低成本统计类 patch。
- 前端显示预算耗尽。

---

## 14. API 设计

新增 router：

```txt
backend/app/routers/evolution.py
backend/app/schemas/evolution.py
```

### 14.1 Endpoints

```txt
GET    /api/evolution/overview
GET    /api/evolution/signals
GET    /api/evolution/patches
GET    /api/evolution/patches/{patch_id}
POST   /api/evolution/patches/{patch_id}/evaluate
POST   /api/evolution/patches/{patch_id}/apply
POST   /api/evolution/patches/{patch_id}/reject
POST   /api/evolution/patches/{patch_id}/rollback
GET    /api/evolution/prompt-experiments
POST   /api/evolution/prompt-experiments/{id}/promote
GET    /api/evolution/training-samples
POST   /api/evolution/training-samples/export
GET    /api/evolution/fine-tune-jobs
POST   /api/evolution/fine-tune-jobs
GET    /api/evolution/worker-status
```

### 14.2 Overview 响应

```json
{
  "today_signals": 12,
  "today_patches": 5,
  "applied_patches": 2,
  "pending_review": 3,
  "rolled_back": 0,
  "prompt_experiments_running": 1,
  "training_samples_total": 320,
  "daily_cost_used": 0.83,
  "daily_cost_limit": 2.0,
  "safety_mode": "normal"
}
```

---

## 15. 前端实施需求

### 15.1 新增页面

```txt
frontend/src/pages/EvolutionPage.tsx
frontend/src/pages/EvolutionPage.css
```

### 15.2 新增组件

```txt
frontend/src/components/evolution/EvolutionOverviewCards.tsx
frontend/src/components/evolution/PatchQueueTable.tsx
frontend/src/components/evolution/PatchDetailDrawer.tsx
frontend/src/components/evolution/PromptExperimentPanel.tsx
frontend/src/components/evolution/TrainingSamplePanel.tsx
frontend/src/components/evolution/FineTuneJobPanel.tsx
frontend/src/components/evolution/EvolutionWorkerStatus.tsx
frontend/src/components/evolution/SafetyBudgetCard.tsx
```

### 15.3 页面布局

```txt
顶部：进化总览 KPI
左侧：Patch 队列
右侧：Patch 详情 / 风险 / before-after / 操作按钮
中部：Prompt 实验
底部：训练样本与 FineTune Job
```

### 15.4 操作规则

- low risk patch 显示“已自动应用”。
- medium risk patch 显示“批准 / 拒绝 / 查看评估”。
- high risk patch 只允许“复制建议 / 拒绝”。
- applied patch 显示“回滚”。
- rollback 必须二次确认。

---

## 16. 代码质量约束

### 16.1 文件大小限制

新增代码必须遵守：

| 类型 | 最大建议行数 |
|---|---:|
| service 单文件 | 300 行 |
| router 单文件 | 250 行 |
| schema 单文件 | 250 行 |
| React 页面 | 300 行 |
| React 组件 | 180 行 |
| 单个函数 | 80 行 |
| 单个类 | 300 行 |

超过限制必须拆分。

### 16.2 分层规则

```txt
router       只做参数解析、权限、调用 service
service      业务逻辑
models       ORM 定义
schemas      Pydantic DTO
workers      调度循环
agents       LLM agent 定义
frontend api 只封装请求
frontend page 只组合组件
component    展示和局部交互
```

### 16.3 依赖规则

允许：

```txt
router -> service -> model
worker -> service
service -> service
agent -> prompt_engine / llm_router
```

禁止：

```txt
model -> service
schema -> service
router -> worker internals
frontend component -> raw fetch scattered everywhere
pipeline -> evolution implementation details
```

### 16.4 错误处理

- 自动任务失败必须落库。
- Worker 不允许吞异常后无记录。
- patch 应用失败必须保留 `evaluation_result` 和 `error`。
- LLM 失败不得导致主写作任务整体崩溃，除非当前步骤不可降级。

### 16.5 日志与审计

所有自动修改必须记录：

- actor
- reason
- before
- after
- patch_id
- source_signal_ids
- rollback_json

---

## 17. 测试计划

### 17.1 后端单元测试

新增测试文件：

```txt
backend/app/tests/test_evolution_patch_service.py
backend/app/tests/test_evolution_analyzer.py
backend/app/tests/test_prompt_experiment.py
backend/app/tests/test_memory_impact.py
backend/app/tests/test_skill_impact.py
backend/app/tests/test_training_sample_builder.py
backend/app/tests/test_evolution_safety.py
backend/app/tests/test_deepstudy_no_fake_complete.py
```

### 17.2 必测场景

| 测试 | 预期 |
|---|---|
| 低分章节生成 patch | 生成 prompt_patch / skill_patch |
| 高分章节生成 skill | 生成 skill_card_patch |
| 重复 patch | 标记 duplicate |
| 无 rollback 自动应用 | 禁止应用 |
| 用户锁定 Prompt | 不自动覆盖 |
| permanent memory patch | 生成 change request，不直接改 |
| Prompt 实验通过 | candidate 晋级 active |
| Prompt 实验失败 | candidate rejected |
| DeepStudy 无 handler | 不标记 completed |
| 预算耗尽 | 停止 LLM 评估，不停止 signal 收集 |

### 17.3 前端测试建议

如果当前前端没有测试体系，先不引入复杂测试框架。至少保证：

- TypeScript `tsc --noEmit` 通过。
- API 类型正确。
- 页面空态、加载态、错误态完整。
- applied / pending / rejected 状态展示正确。

---

## 18. 实施顺序

### Sprint 1：可信 DeepStudy + Evolution 基础

1. 修复 DeepStudy 无 handler 自动完成。
2. 补 `EvolutionSignal` 模型。
3. 补强 `EvolutionPatch` 字段。
4. 新建 `evolution/collector.py`。
5. 新建 `evolution/analyzer.py`。
6. 新建 `evolution/patch_service.py`。
7. `ChapterPipeline` 接入 `on_chapter_pipeline_completed`。
8. 新增 patch 查询 API。
9. 添加后端测试。

交付：章节完成后自动产生可追踪 patch。

### Sprint 2：Patch 评估与安全应用

1. 新建 `evaluator.py`。
2. 新建 `safety.py`。
3. 新建 `applier.py`。
4. 支持 low risk 自动应用。
5. 支持 rollback。
6. 支持 budget limit。
7. 新增 apply/reject/rollback API。
8. 添加测试。

交付：patch 可评估、可应用、可回滚。

### Sprint 3：Prompt 实验系统

1. 新增 `PromptExperiment` 模型。
2. 新建 `prompt_experiment.py`。
3. 支持 candidate PromptVersion。
4. 支持 3 样本 replay。
5. 支持晋级 active。
6. 回填 `last_effect_score`。
7. 添加测试。

交付：Prompt 可以自动生成候选并通过回放晋级。

### Sprint 4：Evolution Center 前端

1. 新增 `/evolution` 路由。
2. 新增 overview cards。
3. 新增 patch queue。
4. 新增 patch detail drawer。
5. 新增 prompt experiment panel。
6. Dashboard 加进化状态入口。
7. `tsc --noEmit` 通过。

交付：用户能看到系统如何进化，并控制高风险 patch。

### Sprint 5：SkillCard 与记忆收益归因

1. Skill 注入写作链路。
2. 写入 `SkillUsageEvent`。
3. 更新 `SkillCard.success_score`。
4. 记忆 access log 关联章节结果。
5. 更新 memory health_score。
6. 冲突记忆生成 patch。
7. 添加测试。

交付：技能和记忆开始优胜劣汰。

### Sprint 6：ModelQualityStat 接入路由

1. 聚合模型质量收益。
2. ModelSelector 读取质量统计。
3. auto 模式调整候选排序。
4. manual 模式不覆盖。
5. 前端模型观测展示质量收益。
6. 添加测试。

交付：模型选择根据实际写作收益持续优化。

### Sprint 7：TrainingSample 与导出

1. 新增 `TrainingSample`。
2. 构建 SFT 样本。
3. 构建 rewrite 样本。
4. 构建 preference pair。
5. JSONL 导出。
6. 前端训练样本面板。
7. 添加测试。

交付：系统自动沉淀可训练数据。

### Sprint 8：全天候 Worker

1. 新增 `evolution_worker.py`。
2. 新增 `evaluation_worker.py`。
3. 新增 `finetune_worker.py`。
4. WorkerController 接入新 worker。
5. Worker 状态 API。
6. 预算、安全模式、熔断。
7. 添加测试。

交付：系统可 24/7 自动运行。

### Sprint 9：Fine-tune Adapter

1. 新增 `FineTuneJob`。
2. 新增 fine-tune adapter 接口。
3. 支持至少一个 Provider。
4. 支持上传数据集。
5. 支持创建和轮询 job。
6. 微调结果注册为模型。
7. 评测通过后加入候选池。

交付：可从 NovelForge 数据资产训练专属模型。

---

## 19. MVP 范围

必须先做 MVP，不要一次性铺满。

MVP 包含：

1. DeepStudy 禁止假完成。
2. `EvolutionSignal`。
3. `EvolutionPatch` 补强。
4. `EvolutionService.on_chapter_pipeline_completed()`。
5. 低分章节自动生成 patch。
6. Patch 查询 API。
7. 简单 Evolution 页面。
8. 基础测试。

MVP 不包含：

- Fine-tune。
- LoRA。
- 大规模 Prompt 回放。
- 全自动高风险应用。
- 复杂前端图表。

MVP 验收：

```txt
跑完一章
→ 自动收集信号
→ 自动归因
→ 自动生成 EvolutionPatch
→ 前端可查看 patch
→ patch 有风险等级、原因、目标、before/after
→ 不破坏现有写作流程
```

---

## 20. 最终验收标准

系统完成后应满足：

- 写作任务能自动产生学习信号。
- DeepStudy 不会假完成。
- 失败能生成修复建议。
- 成功能沉淀技能和训练样本。
- Prompt 能通过实验晋级。
- 记忆能自动升降权。
- 模型路由能根据实际质量调整。
- 低风险 patch 可自动应用。
- 所有自动改动可审计、可回滚。
- Worker 可 24/7 运行且有预算限制。
- 前端能完整查看和控制进化过程。
- 新代码不继续制造大文件和跨层耦合。
