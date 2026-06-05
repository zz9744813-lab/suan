# P0 Model Failover + NF2 自动工厂 — 最终验收清单

**日期**: 2026-06-05
**版本**: 0.2.0 (S1-S6 全部完成)
**提交范围**: 15 个 backend 文件修改/新建 + 3 个 frontend 文件修改/新建

---

## 一、验收方式

1. 启动后端: `cd backend && python -m uvicorn app.main:app --reload`
2. 启动前端: `cd frontend && npm run dev`
3. 按下方「验证步骤」逐项检查
4. 所有 ✅ 通过即验收合格

---

## 二、已修复 Bug (S1+S2) — 验证步骤

### ✅ BUG-1: `_prepare_payload()` JSON 污染修复
**文件**: `backend/app/services/llm/client.py`
**验证**:
```bash
# 1. 检查代码逻辑
python -c "from app.services.llm.client import LLMClient; import inspect; src = inspect.getsource(LLMClient._prepare_payload); assert 'need_json' in src and 'response_format' in src; print('OK: JSON injection is conditional')"

# 2. 实际验证: 创建一个不需要 JSON 的 agent task (如 drafter),
#    查看 LLM 调用日志中是否还有 "只输出一个 JSON 对象" 的系统提示
```
**预期**: Drafter/Rewriter 的正文输出不再包含 JSON 格式残留

### ✅ BUG-2: fallback 候选 score=0.1 固定分修复
**文件**: `backend/app/services/model_selector.py` (L~475)
**验证**:
```bash
# 检查代码中已无硬编码 0.1
grep -n "score=0.1" backend/app/services/model_selector.py || echo "OK: 无固定分"
grep -n "fb_score" backend/app/services/model_selector.py | head -3
```
**预期**: fallback 候选评分基于 provider 健康分 × 0.75 衰减，上限 0.65

### ✅ BUG-3: Worker 延迟重试 + `not_before_at`
**文件**: `backend/app/models/task.py`, `backend/app/workers/worker.py`
**验证**:
```bash
# 1. 检查字段存在
python -c "from app.models.task import AgentTask; assert hasattr(AgentTask, 'not_before_at'); print('OK: not_before_at field exists')"

# 2. 检查 Worker 查询条件包含 not_before_at 过滤
python -c "from app.workers.worker import Worker; import inspect; src = inspect.getsource(Worker._tick); assert 'not_before_at' in src; print('OK: Worker filters by not_before_at')"

# 3. 检查 _mark_task_failed 有指数退避逻辑
python -c "from app.workers.worker import Worker; import inspect; src = inspect.getsource(Worker._mark_task_failed); assert 'delay_s' in src and 'retry_count' in src; print('OK: exponential backoff implemented')"
```
**预期**: 任务失败后 30s/60s/120s 指数退避重试，耗尽 max_retries 才标 failed

### ✅ BUG-4+5: fallback 多候选链
**文件**: `backend/app/services/llm/router.py` (`_try_fallback`)
**验证**:
```bash
# 检查代码结构
python -c "from app.services.llm.router import LLMRouter; import inspect; src = inspect.getsource(LLMRouter._try_fallback); assert 'for attempt_no' in src and 'failed_set' in src and 'MAX_FALLBACK_ATTEMPTS' in src; print('OK: multi-candidate fallback chain')"
```
**预期**: fallback 最多尝试 2 个候选，跳过已失败 provider/model

### ✅ BUG-6: 健康探针格式统一
**文件**: `backend/app/services/provider_health.py`
**验证**:
```bash
python -c "from app.services.provider_health import ProviderHealthService; import inspect; src = inspect.getsource(ProviderHealthService.check_provider); assert 'auto_probe' in src and 'existing_full' in src; print('OK: lightweight probe preserves UI probe data')"
```
**预期**: Worker 轻量探针不再覆盖 UI 探针写入的详细 `last_health_full`

---

## 三、新增功能 (S3-S6) — 验证步骤

### ✅ S3: AgentRunRecorder + Observability API
**文件**: `backend/app/services/agent_run_recorder.py`, `backend/app/routers/model_observability.py`
**验证**:
```bash
# 1. 检查端点注册
curl -s http://127.0.0.1:8000/api/model-observability/summary | python -m json.tool

# 2. 检查 events 端点
curl -s "http://127.0.0.1:8000/api/model-observability/events?limit=10" | python -m json.tool

# 3. 检查 providers 端点
curl -s http://127.0.0.1:8000/api/model-observability/providers | python -m json.tool
```
**预期**: 三个端点均返回 `{ok: true, data: ...}`，无 500 错误

### ✅ S4: PromptAutoBinder
**文件**: `backend/app/services/prompt_auto_binder.py`
**验证**:
```bash
# 1. 检查服务可导入
python -c "from app.services.prompt_auto_binder import get_prompt_auto_binder; print('OK')"

# 2. 检查 PromptEngine 已集成 AutoBinder
python -c "from app.services.prompt_engine import PromptEngine; import inspect; src = inspect.getsource(PromptEngine.resolve_for_agent); assert 'prompt_auto_binder' in src; print('OK: PromptEngine integrates AutoBinder')"
```
**预期**: Agent 首次运行某 genre 时，若找不到 prompt 映射，自动触发绑定

### ✅ S5-T1: 评论自动流
**文件**: `backend/app/routers/reviews.py` (POST `/reviews/auto-create`)
**验证**:
```bash
curl -s -X POST http://127.0.0.1:8000/api/reviews/auto-create \
  -H "Content-Type: application/json" \
  -d '{"agent_task_id":1,"project_id":1,"content":"测试评论","agent_key":"critic","severity":"medium"}' | python -m json.tool
```
**预期**: 返回 `{ok: true, data: {comment: {...}, triage_enqueued: bool}}`

### ✅ S5-T2: 审计日志
**文件**: `backend/app/models/audit_log.py`, `backend/app/routers/audit.py`, `backend/app/services/audit_service.py`
**验证**:
```bash
# 1. 检查端点
curl -s "http://127.0.0.1:8000/api/audit/logs?limit=5" | python -m json.tool

# 2. 检查 recent 端点
curl -s "http://127.0.0.1:8000/api/audit/logs/recent?limit=5" | python -m json.tool

# 3. 检查 stats 端点
curl -s "http://127.0.0.1:8000/api/audit/stats/by-event?days=7" | python -m json.tool
```
**预期**: 三个端点均正常返回，无 500

### ✅ S6: 前端 ModelObservabilityPanel
**文件**: `frontend/src/components/models/ModelObservabilityPanel.tsx`
**验证**:
1. 打开前端 http://localhost:5173/model-observability
2. 检查是否显示「模型可观测性」标题
3. 检查 4 个概览卡片（总调用/成功率/平均延迟/总 Token）
4. 检查 Provider 统计表格
5. 检查最近事件列表

**预期**: 页面正常渲染，无白屏/崩溃

---

## 四、全量 import 验证 (已自动通过)

```bash
cd backend
python -c "
import importlib
mods = [
    'app.models.task', 'app.models.audit_log',
    'app.services.llm.client', 'app.services.llm.router',
    'app.services.model_selector', 'app.services.provider_health',
    'app.services.agent_run_recorder', 'app.services.audit_service',
    'app.services.prompt_auto_binder', 'app.services.prompt_engine',
    'app.workers.worker',
    'app.routers.model_observability', 'app.routers.audit', 'app.routers.reviews',
    'app.main',
]
for m in mods:
    importlib.import_module(m)
    print(f'  OK: {m}')
print('ALL MODULES IMPORTED SUCCESSFULLY')
"
```

---

## 五、已知问题 (非阻塞)

| 问题 | 位置 | 影响 | 建议 |
|------|------|------|------|
| `PageTopbar.tsx` `title` 属性类型错误 | `frontend/src/components/layout/PageTopbar.tsx:115` | TypeScript 编译报错，但运行正常 | 已在 P0 存在，非本轮引入 |
| pydantic `model_name` 命名空间警告 | `backend/app/services/model_selector.py` | 运行警告，不影响功能 | 建议后续加 `model_config['protected_namespaces'] = ()` |

---

## 六、文件变更清单

### Backend (修改 8 + 新建 5 = 13)

| 文件 | 类型 | 说明 |
|------|------|------|
| `app/services/llm/client.py` | 修改 | BUG-1: 条件化 JSON 系统提示注入 |
| `app/services/model_selector.py` | 修改 | BUG-2: fallback 候选真实评分 |
| `app/models/task.py` | 修改 | BUG-3: 新增 `not_before_at` 字段 |
| `app/workers/worker.py` | 修改 | BUG-3: 延迟重试 + 指数退避 |
| `app/services/llm/router.py` | 修改 | BUG-4+5: fallback 多候选链 |
| `app/services/provider_health.py` | 修改 | BUG-6: 探针格式统一 |
| `app/services/prompt_engine.py` | 修改 | S4: 集成 PromptAutoBinder |
| `app/main.py` | 修改 | 注册 observability + audit 路由 |
| `app/services/agent_run_recorder.py` | 新建 | S3: AgentRun 记录服务 |
| `app/routers/model_observability.py` | 新建 | S3: 可观测性 REST API |
| `app/services/prompt_auto_binder.py` | 新建 | S4: 自动 prompt 绑定 |
| `app/models/audit_log.py` | 新建 | S5-T2: 审计日志 ORM |
| `app/services/audit_service.py` | 新建 | S5-T2: 审计日志 Service |
| `app/routers/audit.py` | 新建 | S5-T2: 审计日志 REST API |
| `app/schemas/audit.py` | 新建 | S5-T2: 审计日志 Schemas |

### Frontend (修改 2 + 新建 1 = 3)

| 文件 | 类型 | 说明 |
|------|------|------|
| `src/api/index.ts` | 修改 | 新增 observability API 函数 |
| `src/App.tsx` | 修改 | 注册 `/model-observability` 路由 |
| `src/components/models/ModelObservabilityPanel.tsx` | 新建 | S6: 可观测性面板组件 |

---

## 七、验收结论

- [ ] 后端启动无报错
- [ ] 前端编译无报错 (除预-existing PageTopbar 问题)
- [ ] 全部 6 个 Bug 修复验证通过
- [ ] 全部 4 个新功能验证通过
- [ ] API 端点全部可访问

**验收人**: _________________ **日期**: _________________
