# 后端「真正静默」异常精确定位 (Phase 2.3b)

筛选条件：`except` 块的 body **仅含** `pass` / `...` / 注释（无任何日志、记录、状态变更、raise、return）。

总数: **19**

| 路径 | 行号 | 异常类 | body 详情 |
|------|----:|--------|----------|
| `backend/app/agents/base.py` | 204 | `json.JSONDecodeError` | `pass` |
| `backend/app/agents/base.py` | 251 | `json.JSONDecodeError` | `pass` |
| `backend/app/agents/chief.py` | 47 | `json.JSONDecodeError` | `pass` |
| `backend/app/agents/discussion_orchestrator.py` | 239 | `Exception` | `pass` |
| `backend/app/routers/audit.py` | 61 | `ValueError` | `pass` |
| `backend/app/routers/audit.py` | 67 | `ValueError` | `pass` |
| `backend/app/routers/discussion.py` | 215 | `Exception` | `pass` |
| `backend/app/routers/discussion.py` | 354 | `Exception` | `pass` |
| `backend/app/routers/study.py` | 594 | `OSError` | `pass` |
| `backend/app/services/llm/router.py` | 393 | `Exception` | `pass` |
| `backend/app/tests/test_deepstudy_r25.py` | 161 | `ValidationError` | `pass` |
| `backend/app/tests/test_study_batch_upload.py` | 70 | `urllib.error.HTTPError` | `pass` |
| `backend/app/workers/pipeline.py` | 322 | `json.JSONDecodeError` | `pass` |
| `backend/app/workers/worker.py` | 196 | `asyncio.TimeoutError` | `pass` |
| `backend/app/workers/worker.py` | 212 | `asyncio.TimeoutError` | `pass` |
| `backend/app/workers/worker.py` | 229 | `asyncio.TimeoutError` | `pass` |
| `backend/app/workers/worker.py` | 246 | `asyncio.TimeoutError` | `pass` |
| `backend/app/workers/worker.py` | 265 | `asyncio.TimeoutError` | `pass` |
| `backend/app/workers/worker.py` | 288 | `asyncio.TimeoutError` | `pass` |

## 综合判断

🟡 存在 19 处『静默吞异常』，建议确认是否有意为之：
- `backend/app/agents/base.py:204` —— json.JSONDecodeError: pass
- `backend/app/agents/base.py:251` —— json.JSONDecodeError: pass
- `backend/app/agents/chief.py:47` —— json.JSONDecodeError: pass
- `backend/app/agents/discussion_orchestrator.py:239` —— Exception: pass
- `backend/app/routers/audit.py:61` —— ValueError: pass
- `backend/app/routers/audit.py:67` —— ValueError: pass
- `backend/app/routers/discussion.py:215` —— Exception: pass
- `backend/app/routers/discussion.py:354` —— Exception: pass
- `backend/app/routers/study.py:594` —— OSError: pass
- `backend/app/services/llm/router.py:393` —— Exception: pass
- `backend/app/tests/test_deepstudy_r25.py:161` —— ValidationError: pass
- `backend/app/tests/test_study_batch_upload.py:70` —— urllib.error.HTTPError: pass
- `backend/app/workers/pipeline.py:322` —— json.JSONDecodeError: pass
- `backend/app/workers/worker.py:196` —— asyncio.TimeoutError: pass
- `backend/app/workers/worker.py:212` —— asyncio.TimeoutError: pass
- `backend/app/workers/worker.py:229` —— asyncio.TimeoutError: pass
- `backend/app/workers/worker.py:246` —— asyncio.TimeoutError: pass
- `backend/app/workers/worker.py:265` —— asyncio.TimeoutError: pass
- `backend/app/workers/worker.py:288` —— asyncio.TimeoutError: pass