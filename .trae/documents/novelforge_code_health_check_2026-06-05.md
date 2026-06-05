# NovelForge 2.0 整体代码体检（结构 + 质量 + 测试）— 实施计划

> 模式：Plan Mode（只读）。所有动作仅用只读命令（Glob/Grep/Read/py_compile/pytest --collect-only 等）。极少数带副作用的步骤（pytest 实跑、前端 build）会显式标注「可选 · 需用户授权」。

---

## Summary

对项目 `f:\kelaode\Data\Agents\zhongji8633\wudi8633` 做一次**不修改任何源代码**的综合代码体检，覆盖三大维度：

1. **结构概览**：代码体量、模块拓扑、关键入口、依赖关系
2. **代码质量**：语法可编译性、未捕获异常、明显 bug、风格/反模式
3. **测试情况**：`app/tests/` 与根目录 `test_*.py` 的关系、pytest 收集是否成功、前端是否存在测试体系

最终交付：
- **最终报告**：`f:\kelaode\Data\Agents\zhongji8633\wudi8633\CODE_HEALTH_REPORT.md`
- **中间产物**：`CODE_HEALTH_01_*.md` ~ `CODE_HEALTH_13_*.md`（同目录），用于在最终报告中溯源

---

## Current State Analysis

### A. 项目阶段（来自文档）
- `docs/MASTER_EXECUTION_PLAN.md`：Sprint 1-6 全部完成，代码审查日期 2026-06-05
- `docs/ACCEPTANCE_CHECKLIST.md`：v0.2.0 (S1-S6 全部完成)
- `docs/P5_联调验收手册.md`：上次 P5 验收 2026-06-04

**判断**：本次体检是 P5 验收 push 前的最后一道质量门。

### B. 后端（Python FastAPI）
- `backend/pyproject.toml`：
  - 项目名 `novelforge-backend` v0.1.0，Python `>=3.11`
  - 依赖：fastapi 0.115、sqlalchemy 2.0、pydantic 2.9、aiosqlite、httpx、sse-starlette、tenacity、pypdf/python-docx/bs4/lxml/ebooklib
  - dev 依赖：pytest 8.3、pytest-asyncio 0.24、ruff 0.7
  - pytest 配置：`asyncio_mode = "auto"`、`testpaths = ["app/tests"]`
- `app/` 下 **20 个子包**、**160 个 .py 文件**
- 关键入口 `backend/app/main.py`：FastAPI 实例 + lifespan（init_db + seed + event_bus + worker.stop），注册 24 个 router + 全局 `APIError` 处理器
- 已知大型模块（按字符数）：
  - `routers/study.py` ~ 91.5k
  - `routers/reviews.py` ~ 45.8k
  - `services/agent_memory_service.py` ~ 37.3k
  - `services/llm/client.py` ~ 38.2k
  - `seed.py` ~ 33.9k
  - `workers/pipeline.py` ~ 32k

### C. 后端测试分布（重要）
- `app/tests/`：**20 个 pytest 风格** 文件
  - 8 个基础服务回归（circuit_breaker、provider_health、prompt_auto_binder、llm_router_fallback、llm_client_prompt_mode、model_selector_failover、worker_retry_delay、agent_run_recorder）
  - 12 个业务 sprint 回归（p5_regression、deepstudy_r25、study_relationship_enrich_r24、graph_interaction_r23、bulk_limit_r21、router_r21、study_batch_upload、study_foreshadows_endpoint、graph_materialise_extended、study_relationships、study_behavior_extract、study_chapterize）
- `backend/` 根目录：**18 个 test_*.py + 2 个 verify_*.py = 20 个独立脚本**
  - 经 `test_p1_smoke.py` 确认这是**显式不依赖 pytest** 的独立脚本（用 `httpx + ASGITransport` 跑 FastAPI）
  - **pytest 不会自动收集它们**（不在 testpaths，结构独立）
- `.gitignore` 已忽略 `backend/tests/` 目录

### D. 前端（React + Vite + TS）
- `frontend/package.json`：
  - 脚本仅有 `dev` / `build` / `preview`，**无 `test` 脚本**
  - 依赖：React 18.3、react-router-dom 6.27、zustand 4.5、@dnd-kit/{core,sortable,utilities}
  - devDeps：TypeScript 5.6、Vite 5.4、@vitejs/plugin-react 4.3
  - **没有 vitest / jest / playwright 依赖**
- `frontend/src/`：**108 个 .ts/.tsx 文件**
  - 组织：api/、components/{chapter,dashboard,layout,model-observability,models,project,prompts,reviews,shelf,worker}、hooks/、lib/、pages/、stores/、styles/、types/
- **前端完全无测试**：glob `**/*.test.*` / `**/*.spec.*` / `vitest.config.*` / `jest.config.*` / `playwright.config.*` 均返回空
- 文件中 `describe( / it( / test( / expect(` 的 13 处命中均为 mock 组件 / 调试菜单字符串（`describe('ReviewDebugMenu')` 等），**不是测试文件**

### E. 关键现状判断
1. 后端功能代码量大、模块多，**测试覆盖率结构性不足**（`app/tests/` 20 个 vs `app/` 160 个产品文件）
2. 根目录 20 个 `test_*`/`verify_*` 脚本是**历史 e2e/冒烟脚本**（P1~P4、R15、R19、P0 验收等），与 pytest 测试集割裂
3. 前端**完全没有自动化测试**，TS 类型检查是唯一质量门（`tsc -b` 在 build 中）
4. MASTER_EXECUTION_PLAN 列出 13 个 BUG/GAP（S1-S6 已修），需在体检中逐一复查是否真正修复
5. 单点风险文件：routers/study.py（91k）、seed.py（33k）、workers/pipeline.py（32k）—— 体检应特别关注可读性/可维护性

---

## Proposed Changes

> 每步使用「做什么 / 为什么 / 命令 / 产出物」四要素描述。所有产物写在 `f:\kelaode\Data\Agents\zhongji8633\wudi8633\`。

### Phase 0：探查前准备
- 约定所有中间产物以 `CODE_HEALTH_*` 前缀
- 最终报告固定为 `CODE_HEALTH_REPORT.md`

### Phase 1：结构概览
| Step | 做什么 | 为什么 | 关键命令 / 工具 | 产出物 |
|------|--------|--------|----------------|--------|
| 1.1 | 列 `backend/app/` 所有 .py 文件，按目录聚合行数 | 建立代码热点地图 | `Glob backend/app/**/*.py`、`Get-ChildItem ... -Recurse -Filter *.py \| Measure-Object -Line` | `CODE_HEALTH_01_BACKEND_FILE_INDEX.md` |
| 1.2 | 列 `frontend/src/` 所有 .ts/.tsx，统计 page/component/hook/store 数量 | 摸清前端结构 | `Glob frontend/src/**/*.{ts,tsx}` | `CODE_HEALTH_02_FRONTEND_FILE_INDEX.md` |
| 1.3 | 定位关键入口 + 抽样 router → service → model 调用链 | 摸清依赖骨架 | `Read backend/app/main.py`、`Grep "@router\." backend/app/routers/*.py -n` | 作为报告「架构骨架」节素材 |
| 1.4 | 盘点 docker-compose、Dockerfile、nginx、env example | 部署与运行入口 | `Read docker-compose.yml`、`Read Dockerfile`、`Read docker/nginx.conf`、`Read backend/.env.example`、`Read frontend/.env.development` | 并入最终报告「部署与运行」节 |

### Phase 2：代码质量
| Step | 做什么 | 为什么 | 关键命令 / 工具 | 产出物 |
|------|--------|--------|----------------|--------|
| 2.1 | 对 `app/` 全部 .py 跑 `py_compile` | 确认每个文件至少能解析 | `python -m py_compile <file>` 逐文件 | `CODE_HEALTH_03_PY_COMPILE.md` |
| 2.2 | 跑 `tsc --noEmit` 看 TS 错误 | 前端无测试，类型检查是唯一机械化质量门 | `cd frontend ; npx tsc -b --noEmit` | `CODE_HEALTH_04_TSC_TYPECHECK.md` |
| 2.3 | 未处理异常扫描 | 找裸 except / 捕获后 pass | `Grep "except: *$" backend/app -n`、`Grep "except Exception as" backend/app -n`、`Grep "^\s*pass$" backend/app -n` | `CODE_HEALTH_05_EXCEPTION_PATTERNS.md` |
| 2.4 | 明显 bug 模式复查 + 摸存量 | 复查 MASTER_EXECUTION_PLAN §0 的 13 个 BUG/GAP | `Grep "score=0\.1" backend/app/services/model_selector.py -n`、`Grep "JSON" backend/app/services/llm/client.py -n -C 2`、`Grep "not_before_at" backend/app/models/task.py -n`、`Grep "TODO\|FIXME\|XXX\|HACK" backend/app -n`、`Grep "print(" backend/app -n` | `CODE_HEALTH_06_BUG_RECHECK.md`（每条 BUG 标「已修/未修/疑似」三态） |
| 2.5 | 风格/反模式 | 行长 > 200 函数、类 > 1500 行、重复字符串 | `ruff check backend/app --select C901`（如已装）；`Grep "^\s*def \|^\s*async def " backend/app` 配合文件长度 | `CODE_HEALTH_07_STYLE_HOTSPOTS.md` |
| 2.6 | 关键路径可运行性 | 仅 `import` 整个后端包看是否能加载 | `python -c "import app.main; print('ok')"` | `CODE_HEALTH_08_IMPORT_OK.md` |

### Phase 3：测试情况
| Step | 做什么 | 为什么 | 关键命令 / 工具 | 产出物 |
|------|--------|--------|----------------|--------|
| 3.1 | pytest 收集可行性 | 看 `app/tests/` 能否被全部发现 | `cd backend ; python -m pytest app/tests --collect-only -q` | `CODE_HEALTH_09_PYTEST_COLLECT.md` |
| 3.2 | pytest 实跑（**可选 · 需用户授权**） | 给出「通过率基线」 | `cd backend ; python -m pytest app/tests -q --tb=line` | `CODE_HEALTH_10_PYTEST_RESULTS.md`（通过 / 失败 / 跳过 / 错误数） |
| 3.3 | 根目录 20 个脚本盘点 | 确认身份（冒烟 / e2e / 调试 / 验收） | `Read` 每个文件前 30 行；`Grep "import pytest\|@pytest\." backend/test_*.py` | `CODE_HEALTH_11_ROOT_SCRIPTS.md`（脚本名 / 类别 / 入口 / 是否在 P5 验收清单中） |
| 3.4 | 前端测试体系盘点 | 确认前端无自动化测试 | `Glob frontend/**/vitest.config.* frontend/**/jest.config.* frontend/**/playwright.config.*`、`Glob frontend/src/**/*.test.* frontend/src/**/*.spec.*` | `CODE_HEALTH_12_FRONTEND_TESTING.md` |
| 3.5 | 测试覆盖度近似估算 | 模块 → 测试映射 | `Get-ChildItem backend/app -Recurse -Filter *.py -File` vs `Get-ChildItem backend/app/tests -Filter test_*.py -File` | `CODE_HEALTH_13_COVERAGE_MAP.md` |

### Phase 4：可选增强（不阻塞报告，需用户授权）
- **4.1** Ruff 全量扫描：`ruff check backend/app --statistics`
- **4.2** OpenAPI 生成检查：`python -c "from app.main import app; import json; json.dump(app.openapi(), open('CODE_HEALTH_OPENAPI.json','w'))"`
- **4.3** 前端 build 干跑：`cd frontend ; npm run build -- --mode development --logLevel info`
- **4.4** 依赖陈旧度：`pip list --outdated --format=json`

### Phase 5：报告汇总
合并所有中间产物到 `CODE_HEALTH_REPORT.md`，结构如下：
1. **执行摘要**：关键数据卡片（产品文件数 / 测试文件数 / tsc 错误数 / pytest 错误数 / ruff 警告数）
2. **项目现状**：项目阶段、后端栈、前端栈、关键模块概览
3. **结构概览**（Phase 1）
4. **代码质量**（Phase 2，按严重度 🔴 P0 / 🟡 P1 / 🟢 P2 排）
5. **测试情况**（Phase 3）
   - 5.1 `app/tests/` 通过率基线
   - 5.2 根目录脚本清单 + 整合建议
   - 5.3 前端测试缺失
6. **风险与建议 Top 10**（风险描述 / 影响面 / 推荐修法）
7. **附录**：所有 `CODE_HEALTH_*.md` / `.json` 清单与引用

---

## Assumptions & Decisions

1. **「只读」边界**：Phase 3.2（pytest 实跑）和 Phase 4.3（npm run build）**严格说不是只读**（会创建临时文件 / build artifacts），但不改源代码。报告里要明确标注「可选步骤，需要用户授权」。其余 Phase 全部只用 `Read / Glob / Grep / py_compile / --collect-only`，绝不动文件。
2. **PowerShell 兼容**：所有命令用 PowerShell 语法，避开被环境吞掉的 `$_`（探查阶段已发现该陷阱）。建议两种形式：
   - 直接调用 Python：`python -c "import os, glob; ..."`
   - 用 Glob/Grep 工具完成
3. **「独立测试脚本」不算正式测试**：根目录 20 个 `test_*.py` / `verify_*.py` 是历史 e2e/冒烟脚本，**不计入测试覆盖率统计**。报告中分两栏：「pytest 体系」「独立 e2e 脚本」分别评估。
4. **不实际调用 LLM/网络**：`service/llm/` 下的代码不实际跑通——只做 import / py_compile。
5. **「明显 bug」标准**：仅指可被 grep 出来、或可由 ruff/pylint 静态发现的模式。需要运行时才能发现的 bug 不在本次范围。
6. **报告路径**：`f:\kelaode\Data\Agents\zhongji8633\wudi8633\CODE_HEALTH_REPORT.md`，所有 `CODE_HEALTH_*.md` 中间产物放同目录。
7. **不动 docker 部署**：docker / compose / nginx 不属于代码质量检查范围，只做存在性盘点。

---

## Verification Steps

执行完后用以下清单验证 `CODE_HEALTH_REPORT.md` 完整性：

| # | 验证项 | 通过条件 | 验证方法 |
|---|--------|----------|----------|
| V1 | 报告文件存在 | `CODE_HEALTH_REPORT.md` 在项目根 | `Glob f:\kelaode\...\CODE_HEALTH_REPORT.md` 命中 1 个 |
| V2 | 三大维度章节齐全 | 含「结构」「质量」「测试」三章 | `Grep "^## " CODE_HEALTH_REPORT.md` ≥ 3 个一级 |
| V3 | 后端文件清单完整 | 报告含 160 个 .py 路径统计 | 与 `Glob backend/app/**/*.py` 数量一致 |
| V4 | 前端文件清单完整 | 报告含 108 个 .ts/.tsx 路径统计 | 与 `Glob frontend/src/**/*.{ts,tsx}` 数量一致 |
| V5 | py_compile 100% 跑过 | Phase 2.1 覆盖 `app/` 所有 .py | 比对 `CODE_HEALTH_03_PY_COMPILE.md` 路径数 vs 160 |
| V6 | pytest 收集可执行 | `CODE_HEALTH_09_PYTEST_COLLECT.md` 给出 test 数量 | 数字应 ≥ 50（粗估） |
| V7 | BUG 复查覆盖 13 条 | 报告对 MASTER_EXECUTION_PLAN §0 13 条 BUG/GAP 逐一标注 | 表格列 ≥ 13 行 |
| V8 | 根目录脚本 20 个全覆盖 | `CODE_HEALTH_11_ROOT_SCRIPTS.md` 含 18+2 行 | 表格行数 = 20 |
| V9 | 前端测试缺失明确指出 | 报告有专门一段说"前端无自动化测试" | `Grep "前端无自动化测试" CODE_HEALTH_REPORT.md` 命中 |
| V10 | Top 10 风险列表 | 报告末尾有"风险与建议 Top 10" | 章节存在 |
| V11 | 所有中间产物可追溯 | 每个结论附 `CODE_HEALTH_XX_*.md` 引用 | 抽 5 条断言，链接可点 |
| V12 | 无源代码被修改 | 体检前后 `git status` 为空 | `git status --short` 输出空（用户提供此环境时验证） |

---

## 关键文件位置速查

- 最终报告：`f:\kelaode\Data\Agents\zhongji8633\wudi8633\CODE_HEALTH_REPORT.md`
- 后端入口：`backend/app/main.py`
- 后端依赖：`backend/pyproject.toml`
- 前端依赖：`frontend/package.json`
- 测试设计：`docs/MASTER_EXECUTION_PLAN.md`
- 验收手册：`docs/P5_联调验收手册.md`
- 验收清单：`docs/ACCEPTANCE_CHECKLIST.md`
- 后端冒烟脚本（典型独立测试）：`backend/test_p1_smoke.py`
- Docker 部署：`docker-compose.yml`
