# 根目录 test_*.py / verify_*.py 盘点 (Phase 3.3)

`backend/` 根目录共有 **20** 个独立脚本（18 个 test_*.py + 2 个 verify_*.py）

这些脚本 **不在 pytest 收集范围**（`pyproject.toml` 的 `testpaths = ["app/tests"]`），是历史 e2e/冒烟/性能/验收脚本。

## 1. 全量清单

| 序号 | 脚本 | 类别 | 大小 | 行数 | 头 10 行摘要 |
|----:|------|------|----:|----:|------------|
| 1 | `test_api_perf.py` | 性能 | 7,339 | 198 | `"""Direct API perf probe: streaming vs non-streaming at various max_tokens. / from __future__ import annotations / import asyncio / import json / import os / import sys` |
| 2 | `test_api_perf2.py` | 性能 | 9,558 | 236 | `"""R15 / input×output perf probe. / from __future__ import annotations / import asyncio / import json / import os / import sys` |
| 3 | `test_draft_timing.py` | 其他 | 2,073 | 60 | `"""Test 4000-token Draft-style generation timing on the real provider.""" / import asyncio / import os / import sys / import time / from app.services.llm.client import (  # noqa: E402` |
| 4 | `test_drafter_r15.py` | Sprint 回归 | 4,890 | 113 | `"""R15 smoke test: render drafter prompt with NEW behavior_patterns + 玄幻 hard rules. / from __future__ import annotations / import asyncio / import json / import os / import sys` |
| 5 | `test_drafter_real.py` | 实跑 | 3,526 | 88 | `"""Run the actual drafter prompt and dump both content and reasoning_content.""" / import asyncio / import os / import sys / import time / import json` |
| 6 | `test_list_models.py` | 环境探测 | 829 | 30 | `"""List models on whitedream to see what's available.""" / import asyncio / import os / import sys / from app.services.llm.client import LLMClient  # noqa: E402` |
| 7 | `test_llm_timeout.py` | 超时/边界 | 2,170 | 65 | `"""Standalone LLM call test — confirm the 300s read timeout is enough. / import asyncio / import os / import sys / import time / from app.core.config import settings  # noqa: E402` |
| 8 | `test_model_selector.py` | 其他 | 2,484 | 75 | `"""S6-T12: test_model_selector / import asyncio / import json / import sys / import httpx / from sqlalchemy import select` |
| 9 | `test_model_speed.py` | 其他 | 2,148 | 70 | `"""Quick speed test for several models on the same provider. / import asyncio / import os / import sys / import time / from app.services.llm.client import (  # noqa: E402` |
| 10 | `test_p1_smoke.py` | 冒烟 | 14,727 | 334 | `"""P1 smoke test: 直接用 FastAPI TestClient 验证 17 端点. / import asyncio / import json / import sys / from datetime import datetime, timedelta / import httpx` |
| 11 | `test_p2_reader_review.py` | P-sprint | 4,047 | 97 | `"""P2 验收脚本 — 调 ReaderReviewService 在 chapter 13 上跑 reader_review. / import asyncio / import json / from app.core.database import session_scope / from app.models.comment_review import ( / from app.serv` |
| 12 | `test_p4_e2e.py` | E2E | 17,390 | 405 | `"""P4 E2E 测试: worker 多任务 dispatcher + 4 个 service 路径. / from __future__ import annotations / import asyncio / import sys / from datetime import datetime, timedelta / from pathlib import Path` |
| 13 | `test_picker_r15.py` | Sprint 回归 | 7,952 | 169 | `"""R15 picker fix test. / from __future__ import annotations / import sys / from app.services.llm.client import _pick_best_content, _extract_answer_from_prose, _looks_like_json_stub` |
| 14 | `test_planner_real.py` | 实跑 | 1,978 | 57 | `"""Run the actual planner prompt (rendered for chapter 12) through the / import asyncio / import os / import sys / import time / from app.services.llm.client import (  # noqa: E402` |
| 15 | `test_r15_e2e.py` | E2E | 3,789 | 106 | `"""R15 streaming + picker E2E test. / from __future__ import annotations / import asyncio / import os / import sys / import time` |
| 16 | `test_rewriter_real.py` | 实跑 | 2,874 | 77 | `"""Run the actual rewriter prompt (with the same critic report) to see / import asyncio / import os / import sys / import time / import json` |
| 17 | `test_safe_json.py` | 工具自检 | 1,729 | 36 | `"""Unit tests for the new brace-balanced _safe_json_loads.""" / from app.agents.base import _safe_json_loads` |
| 18 | `test_step37_content.py` | Step 验证 | 1,914 | 56 | `"""Verify step-3.7-flash output quality (no <think> preamble).""" / import asyncio / import os / import sys / import time / from app.services.llm.client import (  # noqa: E402` |
| 19 | `verify_p0.py` | 验收 | 4,891 | 106 | `"""P0 验收: 验证 P6 评论评审系统 seed 数据完整. / import asyncio / import aiosqlite / import sys / from app.core.config import settings` |
| 20 | `verify_p6_p0.py` | 验收 | 2,720 | 72 | `"""P6 P0 验证脚本: 5 张新表 + 6 新 AgentRole + 5 ReaderAgentProfile + ReviewSettings""" / import asyncio / import aiosqlite / from app.core.config import settings` |

## 2. 特征分析

| 特征 | 数量 |
|------|----:|
| 含 `import pytest` | 0 |
| 使用 `httpx + ASGITransport` | 4 |
| 引用 `app.main` | 2 |

**结论**：
- 仅 **0** 个脚本用 pytest（基本为 0）
- **多数**使用 httpx + ASGITransport 直接跑 FastAPI（**显式避开 pytest capture bug**）
- 这些脚本**无法被 `pytest --collect-only` 收集**（不在 testpaths）

## 3. 按类别

| 类别 | 数量 |
|------|----:|
| 其他 | 3 |
| 实跑 | 3 |
| 性能 | 2 |
| Sprint 回归 | 2 |
| E2E | 2 |
| 验收 | 2 |
| 环境探测 | 1 |
| 超时/边界 | 1 |
| 冒烟 | 1 |
| P-sprint | 1 |
| 工具自检 | 1 |
| Step 验证 | 1 |

## 4. 与 `app/tests/` 关系

| 来源 | 数量 | pytest 可收集 | 体系 |
|------|----:|------|------|
| `app/tests/` | 20 | ✅ 全部 | 单元/回归 |
| `backend/` 根目录 | 20 | ❌ 全部 | 端到端/冒烟/性能/验收 |

**整合建议**：
- 🟡 **建议把 `verify_*.py` 重命名为 `test_verify_*.py` 并移入 `app/tests/`** —— 这样 `pytest app/tests -m verify` 就能纳入回归门
- 🟢 **保留 `test_*real` / `test_*perf` 性能脚本在根目录** —— 它们通常需要特殊环境（真实 LLM API key、计时器），不适合纳入单元测试体系
- 🟢 **`test_safe_json.py` / `test_list_models.py` 类工具自检脚本保留根目录** —— 是开发辅助，不进 CI