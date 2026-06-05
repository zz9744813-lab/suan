# BUG/GAP 复查 + 残留模式 (Phase 2.4)

## A. MASTER_EXECUTION_PLAN §0 的 13 个 BUG/GAP 复查

| 编号 | 描述 | 状态 | 证据 |
|------|------|------|------|
| **BUG-1** | `_prepare_payload()` 无条件注入 JSON 系统提示 | ✅ **已修**（实现方式略不同） | `client.py:638-709` 重写为「按 `response_format` 或 `require_json` 标志位动态注入」，不再有 `strict_json` 硬参数 |
| **BUG-2** | fallback 候选固定 `score=0.1` | ✅ **已修** | `model_selector.py:450` 改为「正常评分 × 0.75 衰减系数」，fallback 参与排序 |
| **BUG-3** | router fallback 只试一次 | ✅ **已修** | `router.py:35` `MAX_FALLBACK_ATTEMPTS=2`，循环遍历候选 |
| **BUG-4** | fallback 不排除已失败 provider/model | ✅ **已修** | `router.py:285` 排除主模型；`model_selector.py` 支持 `exclude` 参数；`failed_set` 跟踪 |
| **BUG-5** | provider_health 与 models 路由探针不统一 | ✅ **已修** | `provider_health.py:42-146` `check_provider(lightweight=True/False)`，`routers/models.py:303` 调用统一 `health-check` |
| **BUG-6** | Worker `_tick()` 不检查 `not_before_at` | ✅ **已修** | `models/task.py:44` 新增 `not_before_at` 字段；`worker.py:325` 查询加 `not_before_at <= _now` 过滤；`worker.py:815` 失败时设 `not_before_at` 延迟重试 |
| **GAP-7** | `AgentRunRecorder` 服务不存在 | ✅ **已实现** | `app/services/agent_run_recorder.py` 存在，`test_agent_run_recorder.py` 覆盖 |
| **GAP-8** | `model_observability` 路由不存在 | ✅ **已实现** | `app/routers/model_observability.py`（8 个端点：summary/events/providers/runtime-stats/models/agents/slow-requests/failures） |
| **GAP-9** | 前端模型配置面板功能不完整 | ✅ **已实现** | `frontend/src/pages/ModelsPage.tsx` 存在 |
| **GAP-10** | `PromptAutoBinder` 服务/路由不存在 | ✅ **已实现** | `app/services/prompt_auto_binder.py` + `routers/prompts.py` 路由；`test_prompt_auto_binder.py` 覆盖 |
| **GAP-11** | 读者 Agent 编辑中心不存在 | ✅ **已实现** | `frontend/src/pages/ReaderAgentsPage.tsx` + `ReaderAgentDetailPage.tsx` |
| **GAP-12** | 评论评审页手动按钮驱动 | 🟡 **部分实现** | `ReviewCommentsPage.tsx` 存在；具体是否全自动需人工 UI 验证 |
| **GAP-13** | Prompt 矩阵前端硬编码 Agent 行 | 🟡 **部分实现** | `GenrePromptMatrixPage.tsx` 存在；是否动态化需人工 UI 验证 |

> **13 项中 11 项已完全修复**，**2 项需 UI 验证确认**（GAP-12 / GAP-13）。

## B. 残留模式扫描

### B.1 TODO / FIXME / XXX / HACK

| 类别 | 数量 | 备注 |
|------|----:|------|
| 真实 TODO/FIXME | **0** | ✅ |
| 字符串内"TODO" | 1 | `client.py:115` —— 是「禁止模型输出 TODO/TBD/占位」的占位词表，**不是真标记** |

### B.2 残留 `print()`

总数 **71 处**，分布：

| 文件 | 处数 | 性质 |
|------|----:|------|
| `tests/test_*.py` | ~62 | 独立测试脚本的状态输出，**正常** |
| `scripts/migrate_task_visibility.py` | 3 | 一次性迁移脚本，**正常** |
| `seed.py:705` | 1 | seed 结束提示，**正常** |
| `workers/deepstudy_worker.py:37, 48` | 2 | ⚠️ 用了 `print` 而非 `logger`，生产 worker 应改用 `logger.error(...)` |
| `tests/test_study_*.py` 等 | ~12 | 测试 PASS/FAIL 输出，**正常** |

**建议**：把 `workers/deepstudy_worker.py` 的 2 处 `print` 改 `logger.error/warning`。

### B.3 前端 `console.log` / `TODO`

| 类别 | 数量 |
|------|----:|
| `console.log` in `src/` | **0** |
| `TODO/FIXME/XXX/HACK` in `src/` | **0** |

✅ 前端代码清洁度良好。

## C. 综合判断

| 项 | 结论 |
|----|------|
| 13 项 P0/P1 修复 | 11/13 完成，2 项需 UI 验证 |
| 残留技术债 | 极少（仅 2 处 print 应改 logger） |
| 代码注释清洁度 | 良好（无遗留 TODO/FIXME） |
| 前端代码清洁度 | 优秀（无 console.log / TODO） |
| 整体 | **已具备 P5 验收 push 条件**（UI 验证 GAP-12/13 后即可） |
