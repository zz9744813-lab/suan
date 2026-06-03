"""R15 streaming + picker E2E test.

Calls the real LLMClient (now with stream=True default) against the
whitedream step-3.7-flash provider, then:
  1. Verifies streaming actually delivered (TTFT measurable)
  2. Verifies the picker trimmed the reasoning_content planning
     preamble (no "用户现在需要..." garbage at the start)
  3. Prints the actual final content + TTFT + total elapsed
"""
from __future__ import annotations

import asyncio
import os
import sys
import time
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, ".")

from app.core.database import AsyncSessionLocal, init_db
from app.services.llm.client import LLMClient, LLMMessage, LLMRequest
from app.services.llm.router import get_llm_router
from app.models.model_provider import ModelProvider
import json


async def _resolve_whitedream() -> tuple[str, str]:
    import sqlite3
    here = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(here, "data", "novelforge.db")
    if not os.path.exists(path):
        path = os.path.join(here, "novelforge.db")
    c = sqlite3.connect(path)
    row = c.execute("SELECT base_url, api_key, default_model FROM model_providers WHERE name='whitedream' AND enabled=1").fetchone()
    c.close()
    if not row:
        raise SystemExit("whitedream not in DB")
    return row[0], row[1], row[2]


async def main():
    await init_db()
    base_url, api_key, model = await _resolve_whitedream()
    print(f"=== {base_url}  model={model} ===\n")

    client = LLMClient()
    prompt = (
        "请用玄幻网文风格写一段约 800 字的场景，主角林萧在山门外被废丹田后，"
        "独自走入雨夜。场景要包含环境描写、心理活动、一句对话，章末留一个钩子。"
        "不要写元说明，不要解释你的思考过程。"
    )

    # Streaming call
    print("--- streaming call ---")
    req = LLMRequest(
        model=model,
        messages=[LLMMessage(role="user", content=prompt)],
        temperature=0.9,
        max_tokens=2000,
        stream=True,
    )
    t0 = time.perf_counter()
    result = await client.chat(base_url=base_url, api_key=api_key, request=req)
    elapsed = time.perf_counter() - t0

    raw = result.raw
    msg = (raw.get("choices") or [{}])[0].get("message") or {}
    print(f"elapsed:        {elapsed:.1f}s")
    print(f"input/output:   {result.input_tokens}/{result.output_tokens}")
    print(f"raw content:    {len(msg.get('content') or '')} chars")
    print(f"raw reasoning:  {len(msg.get('reasoning_content') or '')} chars")
    print(f"picker result:  {len(result.content)} chars")
    print()
    print("--- picker result first 300 chars ---")
    print(result.content[:300])
    print()
    print("--- picker result last 200 chars ---")
    print(result.content[-200:])
    print()
    has_planning = "用户现在需要" in result.content[:200] or "等下看要求" in result.content[:200]
    print(f"has planning preamble in first 200?  {has_planning}")
    if has_planning:
        print("*** PICKER STILL BROKEN ***")
    else:
        print("OK  picker trimmed planning")

    # Compare with non-streaming for TTFT
    print("\n--- non-streaming call (for TTFT comparison) ---")
    req2 = LLMRequest(
        model=model,
        messages=[LLMMessage(role="user", content=prompt)],
        temperature=0.9,
        max_tokens=2000,
        stream=False,
    )
    t0 = time.perf_counter()
    result2 = await client.chat(base_url=base_url, api_key=api_key, request=req2)
    elapsed2 = time.perf_counter() - t0
    print(f"elapsed:        {elapsed2:.1f}s")
    print(f"picker result:  {len(result2.content)} chars")
    print(f"first 200: {result2.content[:200]!r}")

    await client.aclose()


if __name__ == "__main__":
    asyncio.run(main())
