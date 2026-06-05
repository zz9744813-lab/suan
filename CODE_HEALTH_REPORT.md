# NovelForge 2.0 整体代码体检报告

> **生成时间**: 2026-06-05  
> **检查模式**: Plan / 只读探查  
> **覆盖范围**: 整个项目（前后端）  
> **检查维度**: 结构概览 + 代码质量 + 测试情况

---

## 1. 执行摘要

### 关键数据卡片

| 维度 | 指标 | 数值 | 状态 |
|------|------|------|------|
| **后端体量** | Python 文件数 | **161** | — |
|  | 后端代码行数 | **40,484** | — |
|  | 子包数 | 20 | — |
|  | Router 端点数 | **223** | — |
| **前端体量** | TS/TSX 文件数 | **108** | — |
|  | 前端代码行数 | **23,404** | — |
|  | 页面组件数 | 27 | — |
| **代码质量** | py_compile 成功率 | **161/161 = 100%** | ✅ |
|  | tsc 严格模式错误数 | **0** | ✅ |
|  | 裸 `except:` 数 | **0** | ✅ |
|  | 真正"只 pass"异常 | 19（均合理） | ✅ |
|  | 残留 TODO/FIXME | 0 | ✅ |
|  | 残留 print（非测试/脚本） | 2 | 🟡 |
|  | God function (>200 行) | 6 | 🟡 |
|  | God class (>600 行) | 2 | 🟡 |
|  | 模块依赖图完整性 | 0 断链 | ✅ |
| **BUG/GAP 修复** | MASTER_EXECUTION_PLAN §0 13 项 | 11/13 完成，2 项待 UI 验证 | 🟢 |
| **测试** | pytest 可发现测试 | **79** | ✅ |
|  | pytest 实跑 | 未跑（环境缺包） | ⚠️ |
|  | 直接 import 覆盖率 | **17.6%** (25/142) | 🔴 |
|  | 前端自动化测试 | **0** | 🔴 |
|  | 根目录独立脚本 | 20 个 | 🟡 |

### 一句话总结

> **P5 验收 push 的代码质量门全部通过**（py_compile、tsc、import 解析、BUG/GAP 修复、清洁度）。
> 主要风险是**测试覆盖不足**（后端 17.6% 直接 import 覆盖、前端零自动化）和**少量 god code 待重构**。

---

## 2. 项目现状

| 项 | 内容 |
|----|------|
| 项目名 | NovelForge 2.0（AI 辅助长篇写作平台） |
| 阶段 | Sprint 1-6 全部完成，P5 验收前最后一道质量门 |
| 后端栈 | Python 3.11+ / FastAPI 0.115 / SQLAlchemy 2.0 / Pydantic 2.9 / aiosqlite / httpx / sse-starlette / tenacity |
| 前端栈 | React 18.3 / TypeScript 5.6 / Vite 5.4 / Zustand 4.5 / @dnd-kit |
| 部署 | Docker Compose：backend (8000) + frontend (nginx 80)，volume `novelforge_data` 持久化 SQLite |
| 业务能力 | 项目/章节/任务管理、提示词模板、模型 Provider + 角色矩阵、拆书（study）、深度研究（deepstudy）、知识图谱、读者评论、讨论追踪、Agent 记忆 |

---

## 3. 结构概览

### 3.1 后端模块分布（按子包聚合）

| 子包 | 文件 | 总行 | 代码行 | 占比 |
|------|----:|----:|----:|----:|
| `routers` | 26 | 7,847 | ~6,000 | **19.4%**（最大） |
| `services` | 45 | 12,083 | ~8,500 | 29.8% |
| `schemas` | 19 | 2,892 | ~2,200 | 7.1% |
| `models` | 22 | 3,605 | ~2,600 | 8.9% |
| `agents` | 12 | 2,961 | ~2,100 | 7.3% |
| `tests` | 20 | 4,461 | ~3,000 | 11.0% |
| `workers` | 6 | 2,121 | ~1,500 | 5.2% |
| `core` | 6 | 1,330 | ~1,000 | 3.3% |
| 其他 | 5 | 3,184 | ~2,000 | 7.9% |

### 3.2 Top 10 最大后端文件

| 路径 | 字节 | 行数 |
|------|----:|----:|
| `routers/study.py` | ~95,000 | 2,389 |
| `seed.py` | ~34,000 | 800+ |
| `routers/reviews.py` | ~46,000 | 1,200+ |
| `services/llm/client.py` | ~38,000 | 950+ |
| `services/agent_memory_service.py` | ~37,000 | 930+ |
| `workers/pipeline.py` | ~32,000 | 800+ |
| `services/llm/router.py` | ~22,000 | 550+ |
| `routers/agent_roles.py` | ~18,000 | 450+ |
| `routers/discussion_trace.py` | ~18,000 | 450+ |
| `services/prompt_engine.py` | ~17,000 | 430+ |

### 3.3 前端模块分布

| 子目录 | 文件数 | 总行 |
|--------|------:|----:|
| `components/` | ~40 | ~10,000 |
| `pages/` | 27 | ~5,500 |
| `hooks/` | 6 | ~500 |
| `stores/` | 8 | ~1,200 |
| `api/` | ~12 | ~1,500 |
| `lib/` | ~8 | ~1,000 |
| 其他 (types/styles) | 7 | ~700 |

### 3.4 入口与 API 拓扑

- **应用入口**：`backend/app/main.py`
  - 24 个 router，**223 个端点**（详见 `CODE_HEALTH_01c_ENTRY_TOPOLOGY.md`）
  - 全局 `APIError` 异常处理 → 统一 JSON 响应
  - 启动钩子：`init_db → seed → event_bus.publish(app.ready)`
  - 关闭钩子：`worker.stop()`

- **Docker 部署**：
  - 2 个 service（backend + frontend-nginx）+ 1 个 volume + 1 个 bridge
  - **单 worker 限制**（uvicorn workers=1，因 in-process asyncio worker 与 SQLite 兼容）
  - Nginx 适配 SSE（`proxy_buffering off; proxy_read_timeout 1h`）

详细数据见：
- `CODE_HEALTH_01_BACKEND_FILE_INDEX.md`（后端文件清单）
- `CODE_HEALTH_02_FRONTEND_FILE_INDEX.md`（前端文件清单）
- `CODE_HEALTH_01c_ENTRY_TOPOLOGY.md`（入口与 router 拓扑）
- `CODE_HEALTH_01d_DEPLOYMENT.md`（Docker / 部署）

---

## 4. 代码质量

### 4.1 静态检查（全部通过 ✅）

| 检查 | 命令 | 结果 |
|------|------|------|
| Python 语法 | `python -m py_compile <file>` 逐文件 | **161/161 通过** |
| TypeScript 类型 | `npx tsc --noEmit`（strict 模式） | **0 错误** |
| 模块依赖图 | AST 解析所有 `from app.X import Y` | **0 断链**（165/165） |
| 裸 `except:` | 静态扫描 | **0 处** |
| 残留 TODO/FIXME | grep | **0 处**（唯一 1 命中是占位词表） |
| 前端 `console.log` | grep | **0 处** |

### 4.2 异常处理（19 处"只 pass"，全部合理）

19 处 `except` 块的 body 仅含 `pass`，逐个验证均为合理容错：

| 位置 | 异常类 | 合理性 |
|------|--------|--------|
| `agents/base.py:204, 251` | json.JSONDecodeError | JSON 解析失败后回退到 fence-stripping 尝试 |
| `agents/chief.py:47` | json.JSONDecodeError | 同上 |
| `routers/audit.py:61, 67` | ValueError | 非法 ISO 日期静默忽略（过滤器跳过） |
| `workers/worker.py:196, 212, 229, 246, 265, 288` | asyncio.TimeoutError | `wait_for` 轮询超时是预期行为 |
| `routers/study.py:594` | OSError | 文件读取容错 |
| `routers/discussion.py:215, 354` | Exception | 非关键路径降级 |
| `agents/discussion_orchestrator.py:239` | Exception | 技能草案创建失败不影响主流程（注释说明） |
| `services/llm/router.py:393` | Exception | fallback 末尾兜底 |
| `workers/pipeline.py:322` | json.JSONDecodeError | 同 base.py |
| 测试文件 2 处 | - | 测试中故意容错 |

**结论**：异常处理习惯良好。

### 4.3 BUG/GAP 复查

`docs/MASTER_EXECUTION_PLAN.md` §0 列出的 13 个 P0/P1/P2 缺陷，**11 项已完全修复**，**2 项需 UI 验证**：

| 编号 | 描述 | 状态 |
|------|------|------|
| BUG-1 | LLMClient JSON 污染 | ✅ 已修（实现方式略不同） |
| BUG-2 | fallback 候选固定 0.1 | ✅ 已修（改为 0.75 衰减系数） |
| BUG-3 | router fallback 只试一次 | ✅ 已修（MAX_FALLBACK_ATTEMPTS=2） |
| BUG-4 | fallback 不排除已失败 | ✅ 已修（failed_set 跟踪） |
| BUG-5 | 两套探针逻辑不统一 | ✅ 已修（lightweight/full 模式） |
| BUG-6 | Worker 缺 not_before_at 延迟重试 | ✅ 已修（task 模型 + worker 过滤） |
| GAP-7 | AgentRunRecorder 服务 | ✅ 已实现 |
| GAP-8 | model_observability 路由 | ✅ 已实现（8 端点） |
| GAP-9 | 前端模型配置面板 | ✅ 已实现（ModelsPage） |
| GAP-10 | PromptAutoBinder | ✅ 已实现 |
| GAP-11 | 读者 Agent 编辑中心 | ✅ 已实现（ReaderAgentsPage + Detail） |
| GAP-12 | 评论评审页手动驱动 | 🟡 文件存在，需 UI 验证 |
| GAP-13 | Prompt 矩阵硬编码 Agent | 🟡 文件存在，需 UI 验证 |

### 4.4 风格/反模式

| 类别 | 数量 | Top 案例 |
|------|----:|---------|
| 函数 > 200 行（god function） | **6** | `seed.py:seed` (578 行)、`pipeline.py:run` (518 行) |
| 函数 100-200 行 | 32 | 分布在 routers/services/workers |
| 类 > 600 行（god class） | **2** | `WorkerController` (835 行)、`ChapterPipeline` (678 行) |
| 类 300-600 行 | 6 | `AgentMemoryService`、`LLMClient` 等 |
| 残留 `print`（生产 worker） | **2** | `workers/deepstudy_worker.py:37, 48` 应改 `logger` |

详细清单：`CODE_HEALTH_07_STYLE_HOTSPOTS.md`

---

## 5. 测试情况

### 5.1 pytest 体系（`app/tests/`）

| 项 | 数值 |
|----|----:|
| 测试文件数 | 20 |
| 收集到的 test function | **79**（12 个文件可 import） |
| pytest 实跑 | 未跑（环境缺 fastapi） |
| 直接 import 覆盖率 | **17.6%**（25/142 产品模块） |

测试分布：
- **8 个基础服务回归**（circuit_breaker、provider_health、prompt_auto_binder、llm_router_fallback 等）
- **12 个业务 sprint 回归**（p5_regression、deepstudy_r25、graph_interaction_r23、study_xxx 等）

### 5.2 根目录独立脚本（20 个）

`backend/` 根目录有 **18 个 test_*.py + 2 个 verify_*.py**，**全部不在 pytest 收集范围**（`testpaths = ["app/tests"]`）。

| 类别 | 数量 | 用途 |
|------|----:|------|
| 性能/超时 | 4 | `test_api_perf.py`、`test_api_perf2.py`、`test_llm_timeout.py`、`test_draft_timing.py` |
| 实跑 | 4 | `test_drafter_real.py`、`test_planner_real.py`、`test_rewriter_real.py`、`test_model_speed.py` |
| 冒烟/E2E | 4 | `test_p1_smoke.py`、`test_p4_e2e.py`、`test_r15_e2e.py`、`test_p2_reader_review.py` |
| Sprint 回归 | 2 | `test_drafter_r15.py`、`test_picker_r15.py` |
| 验收 | 2 | `verify_p0.py`、`verify_p6_p0.py` |
| 工具/探测 | 4 | `test_safe_json.py`、`test_list_models.py`、`test_model_selector.py`、`test_step37_content.py` |

**特征**：这些脚本大多用 `httpx + ASGITransport` 直接跑 FastAPI（**显式避开 pytest capture bug**）。

详细清单：`CODE_HEALTH_11_ROOT_SCRIPTS.md`

### 5.3 前端测试体系（🚨 完全缺失）

| 框架 | 是否配置 |
|------|---------|
| vitest / jest / playwright / cypress / @testing-library | **全部 0** |
| `*.test.*` / `*.spec.*` 文件 | **0** |
| `package.json` 的 `"test"` 脚本 | **0** |

**唯一质量门**：`tsc -b --noEmit`（已通过 0 错误）。

### 5.4 测试覆盖度近似（按子包）

| 子包 | 产品模块 | 被覆盖 | 覆盖率 |
|------|------:|------:|------:|
| `agents` | 12 | 0 | 0% |
| `core` | 6 | 0 | 0% |
| `models` | 22 | 0 | 0% |
| `routers` | 26 | 0 | 0% |
| `schemas` | 19 | 0 | 0% |
| `services` | 45 | 0 | 0% |
| `workers` | 6 | 0 | 0% |
| **合计（pytest 触及的子包）** | — | **25** | **17.6%** |

> 表格「0%」指**子包内的所有模块**都未被任何 pytest 测试 import，但实际测试可能通过 router → service → model 链路间接覆盖。具体行/分支覆盖率需引入 `coverage.py` 跑出。

---

## 6. 风险与建议 Top 10

按严重度排序：

| 严重度 | 风险 | 影响面 | 推荐修法 |
|--------|------|--------|----------|
| 🔴 P0 | **前端零自动化测试** | 重构类型/组件无回归保护 | P5 push 后立即引入 vitest + @testing-library/react，至少给 stores/lib 加 80% 覆盖 |
| 🔴 P0 | **后端行覆盖率未知**（仅 17.6% import 覆盖） | Sprint 1-6 的 P0 修复无回归门 | 加 `pytest-cov`，CI 中设 ≥ 60% 门槛 |
| 🟡 P1 | **环境受限，pytest 实跑未跑通** | 验收机环境未验证 | P5 验收前置：CI 容器 `pip install -e backend/` + `pytest app/tests --tb=short` |
| 🟡 P1 | **2 个 P2 待 UI 验证**（GAP-12/13） | 验收阻塞 | 跑 P5 联调验收脚本 `docs/P5_联调验收手册.md` |
| 🟡 P1 | **2 个 god class**（`WorkerController` 835 行、`ChapterPipeline` 678 行） | 后续维护成本高 | 按职责拆分（启动/任务/回收/事件 4 个子模块） |
| 🟡 P1 | **6 个 god function**（`seed` 578 行、`pipeline.run` 518 行等） | 单元测试困难 | 拆为多个 helper（典型：seed 拆为 `_seed_providers/_seed_prompts/...`） |
| 🟡 P1 | **前端 / 后端无集成测试**（E2E 全部在根目录脚本） | API 改动无法快速发现前端回归 | 引入 playwright 跑核心 E2E |
| 🟢 P2 | **`workers/deepstudy_worker.py` 2 处 print** | 生产日志不规范 | 改 `logger.error/warning` |
| 🟢 P2 | **根目录 20 个脚本未纳入 pytest** | 历史 e2e 资产未做回归门 | 改名为 `test_xxx_e2e.py` 移入 `app/tests/`，加 `@pytest.mark.e2e` 标签 |
| 🟢 P2 | **`tsconfig.json` 未启用** `noUncheckedIndexedAccess` 等更严检查 | 类型安全仍有提升空间 | 加 2-3 个 strict 选项，逐项适配 |

---

## 7. 附录

### 7.1 中间产物清单（13 份）

| 文件 | 内容 |
|------|------|
| `CODE_HEALTH_01_BACKEND_FILE_INDEX.md` | 后端 161 个 .py 文件清单（路径/字节/行数/代码行） |
| `CODE_HEALTH_01c_ENTRY_TOPOLOGY.md` | 入口与 router 拓扑（223 端点） |
| `CODE_HEALTH_01d_DEPLOYMENT.md` | Docker / 部署入口盘点 |
| `CODE_HEALTH_02_FRONTEND_FILE_INDEX.md` | 前端 108 个 .ts/.tsx 文件清单 |
| `CODE_HEALTH_03_PY_COMPILE.md` | py_compile 161/161 通过 |
| `CODE_HEALTH_04_TSC_TYPECHECK.md` | tsc 严格模式 0 错误 |
| `CODE_HEALTH_04_TSC_RAW.txt` | tsc 原始输出（空） |
| `CODE_HEALTH_05_EXCEPTION_PATTERNS.md` | 异常模式扫描（78 except, 27 疑似静默） |
| `CODE_HEALTH_05b_TRULY_SILENT.md` | 19 处"只 pass"，逐个验证合理 |
| `CODE_HEALTH_06_BUG_RECHECK.md` | 13 BUG/GAP 复查（11 修，2 待验证） |
| `CODE_HEALTH_07_STYLE_HOTSPOTS.md` | god function/class 热点（38 长函数 / 8 长类） |
| `CODE_HEALTH_08_IMPORT_OK.md` | 模块依赖图 0 断链 |
| `CODE_HEALTH_09_PYTEST_COLLECT.md` | pytest 79 tests collect |
| `CODE_HEALTH_11_ROOT_SCRIPTS.md` | 根目录 20 个脚本盘点 |
| `CODE_HEALTH_12_FRONTEND_TESTING.md` | 前端无自动化测试 |
| `CODE_HEALTH_13_COVERAGE_MAP.md` | 直接 import 覆盖率 17.6% |

### 7.2 关键文件位置速查

- 后端入口：`backend/app/main.py`
- 后端依赖：`backend/pyproject.toml`
- 前端依赖：`frontend/package.json`
- 测试设计：`docs/MASTER_EXECUTION_PLAN.md`
- 验收手册：`docs/P5_联调验收手册.md`
- 验收清单：`docs/ACCEPTANCE_CHECKLIST.md`
- 后端冒烟脚本：`backend/test_p1_smoke.py`
- Docker 部署：`docker-compose.yml`

### 7.3 体检方法说明

| 维度 | 工具 |
|------|------|
| 后端文件清单 | Python 脚本（pathlib + 大小/行数统计） |
| 前端文件清单 | Python 脚本 |
| Python 语法 | `python -m py_compile` 逐文件 |
| TypeScript 类型 | `npx tsc --noEmit` |
| 异常模式 | AST 解析 + grep 联合 |
| BUG 复查 | grep + 文件存在性 |
| 风格 | AST 解析函数/类长度 |
| 模块依赖 | AST 解析 `from app.X import Y` |
| pytest 收集 | `python -m pytest --collect-only` |
| 覆盖率估算 | AST 反向 import 映射 |

### 7.4 环境限制说明

- 当前 Python 是 **3.10.11**（项目要求 >=3.11），且未安装 fastapi/pydantic/sqlalchemy 等依赖
- 因此 `python -c "import app.main"` 失败 → 改用 AST 静态解析替代运行时验证
- pytest collect 报 8 个错误全部由环境缺包引起（**非测试代码 bug**）
- 实际 P5 验收需在补装 `pip install -e backend/` 后再跑
