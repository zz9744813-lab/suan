# 测试覆盖度近似估算 (Phase 3.5)

## 方法

- 收集 `app/tests/` 下所有 pytest 测试文件
- 解析每个测试的 `from app.X import ...` 语句
- 反向建立 `app.X` → `[test files]` 映射
- **未导入 = 表面未被覆盖**（不保证覆盖完整，但能反映有/无）

产品模块: **142** 个 .py
测试文件: **20** 个
被至少 1 个测试 import 的产品模块: **25**
未被任何测试 import 的产品模块: **117**

## 1. 直接覆盖率（被 import 的产品模块比例）

- **直接覆盖率**: 25/142 = **17.6%**

## 2. 按子包聚合

| 子包 | 产品模块 | 被覆盖 | 覆盖率 | 缺失模块 |
|------|------:|------:|------:|--------|
| `__init__.py` | 1 | 0 | 0% | `__init__.py` |
| `agents` | 12 | 0 | 0% | `agents/__init__.py`, `agents/base.py`, `agents/chief.py`, `agents/continuity.py`, `agents/critic.py` … +7 |
| `core` | 6 | 0 | 0% | `core/__init__.py`, `core/config.py`, `core/database.py`, `core/errors.py`, `core/events.py` … +1 |
| `models` | 22 | 0 | 0% | `models/__init__.py`, `models/agent_memory.py`, `models/agent_role.py`, `models/audit_log.py`, `models/behavior_card.py` … +17 |
| `prompts` | 3 | 0 | 0% | `prompts/__init__.py`, `prompts/default/__init__.py`, `prompts/default/library.py` |
| `routers` | 26 | 0 | 0% | `routers/__init__.py`, `routers/agent_memory.py`, `routers/agent_roles.py`, `routers/audit.py`, `routers/behavior.py` … +21 |
| `schemas` | 19 | 0 | 0% | `schemas/__init__.py`, `schemas/agent_memory.py`, `schemas/agent_role.py`, `schemas/audit.py`, `schemas/behavior_card.py` … +14 |
| `scripts` | 2 | 0 | 0% | `scripts/__init__.py`, `scripts/migrate_task_visibility.py` |
| `services` | 45 | 0 | 0% | `services/__init__.py`, `services/agent_memory_service.py`, `services/agent_run_recorder.py`, `services/audit_service.py`, `services/behavior_card_service.py` … +40 |
| `workers` | 6 | 0 | 0% | `workers/__init__.py`, `workers/deepstudy_worker.py`, `workers/discussion_recycle_worker.py`, `workers/discussion_worker.py`, `workers/pipeline.py` … +1 |

## 3. 测试文件 → 覆盖的产品模块

| 测试文件 | 覆盖的产品模块数 | 主要覆盖 |
|------|------:|--------|
| `tests/test_p5_regression.py` | 10 | app.core.config, app.main, app.schemas.agent_role, app.schemas.deepstudy, app.schemas.memory_v2 … |
| `tests/test_llm_router_fallback.py` | 4 | app.core.errors, app.services.llm.client, app.services.llm.router, app.services.model_selector |
| `tests/test_deepstudy_r25.py` | 3 | app.routers.deepstudy, app.schemas.deepstudy, app.schemas.study |
| `tests/test_router_r21.py` | 3 | app.core.database, app.models.model_provider, app.services.llm.router |
| `tests/test_provider_health_service.py` | 2 | app.services.llm.client, app.services.provider_health |
| `tests/test_study_foreshadows_endpoint.py` | 2 | app.models.memory, app.schemas.study |
| `tests/test_study_relationship_enrich_r24.py` | 2 | app.prompts.default.library, app.schemas.study |
| `tests/test_agent_run_recorder.py` | 1 | app.services.agent_run_recorder |
| `tests/test_circuit_breaker.py` | 1 | app.services.model_circuit_breaker |
| `tests/test_graph_materialise_extended.py` | 1 | app.schemas.study |
| `tests/test_llm_client_prompt_mode.py` | 1 | app.services.llm.client |
| `tests/test_model_selector_failover.py` | 1 | app.services.model_selector |
| `tests/test_prompt_auto_binder.py` | 1 | app.services.prompt_auto_binder |
| `tests/test_study_behavior_extract.py` | 1 | app.schemas.study |
| `tests/test_study_chapterize.py` | 1 | app.routers.study |
| `tests/test_study_relationships.py` | 1 | app.schemas.study |
| `tests/test_worker_retry_delay.py` | 1 | app.workers.worker |
| `tests/test_bulk_limit_r21.py` | 0 |  |
| `tests/test_graph_interaction_r23.py` | 0 |  |
| `tests/test_study_batch_upload.py` | 0 |  |

## 4. 未被任何测试 import 的模块（潜在盲区）

**142** 个模块未被任何测试直接 import。

按行数排序（关注大型未测试模块）：

| 路径 | 大小 | 行数 |
|------|----:|----:|
| `routers/study.py` | 96,533 | 2,408 |
| `prompts/default/library.py` | 59,250 | 1,122 |
| `routers/reviews.py` | 49,289 | 1,373 |
| `services/llm/client.py` | 41,791 | 1,002 |
| `routers/models.py` | 40,959 | 1,005 |
| `workers/worker.py` | 40,072 | 896 |
| `services/agent_memory_service.py` | 39,335 | 1,045 |
| `workers/pipeline.py` | 33,497 | 823 |
| `routers/deepstudy.py` | 29,256 | 774 |
| `routers/project_memory.py` | 26,551 | 602 |
| `models/deepstudy.py` | 23,896 | 473 |
| `routers/tasks.py` | 22,242 | 541 |
| `routers/graph.py` | 20,263 | 532 |
| `services/model_selector.py` | 20,240 | 509 |
| `routers/agent_roles.py` | 19,652 | 511 |
| `services/review/reader_review_service.py` | 19,556 | 528 |
| `services/review/comment_triage_service.py` | 19,411 | 523 |
| `routers/discussion_trace.py` | 18,442 | 511 |
| `services/llm/router.py` | 17,703 | 413 |
| `schemas/study.py` | 17,456 | 515 |

## 5. 综合判断

- 🟡 **直接 import 覆盖率约 17.6%**
- 测试文件数（20）vs 产品模块数（142），比例 1:7.1
- 已知**未测试**的高风险模块见上表

**说明**：import 覆盖率 ≠ 行/分支覆盖率。本估算只反映「至少有一个测试触达过这个模块」，实际逻辑覆盖可能远低于此。

**后续建议**（不在本次体检范围）：
- 引入 `coverage.py` + `pytest-cov` 跑出真实行覆盖
- 给 `app/services/llm/`、`app/agents/`、`app/workers/` 加更多单元测试
- 给 `app/routers/*.py` 加 FastAPI `TestClient` 集成测试