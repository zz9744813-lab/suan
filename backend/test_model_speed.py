"""Quick speed test for several models on the same provider.

Each model gets a 1000-token request; we report elapsed + tok/s.
We pick the fastest non-reasoning one for the heavy Draft / Rewrite
roles and keep a slower model for the small JSON roles.
"""
import asyncio
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.services.llm.client import (  # noqa: E402
    LLMClient,
    LLMMessage,
    LLMRequest,
)


BASE_URL = os.environ.get("LLM_BASE_URL", "https://your-provider.example/v1")
API_KEY = os.environ.get("LLM_API_KEY", "your-api-key-here")

CANDIDATES = [
    "deepseek-v4-flash",   # baseline
    "step-3.7-flash",      # user-specified reasoning model
    "qwen3.5-122b-a10b",   # Qwen MoE
    "glm-5.1",             # Zhipu
    "kimi-k2.6",           # Moonshot
]

PROMPT = (
    "写一段 800 字左右的玄幻小说片段，主角林萧被宗门逐出山门，"
    "走在雨中。请用白话中文，不要分段标记。"
)


async def time_one(client: LLMClient, model: str) -> tuple[str, float, int, str]:
    req = LLMRequest(
        model=model,
        max_tokens=1000,
        temperature=0.8,
        messages=[LLMMessage(role="user", content=PROMPT)],
    )
    t0 = time.perf_counter()
    try:
        result = await client.chat(base_url=BASE_URL, api_key=API_KEY, request=req)
        elapsed = time.perf_counter() - t0
        return (model, elapsed, result.output_tokens, "ok")
    except Exception as exc:
        elapsed = time.perf_counter() - t0
        return (model, elapsed, 0, f"FAIL: {type(exc).__name__}: {exc!r}")


async def main() -> int:
    client = LLMClient()
    results = []
    for m in CANDIDATES:
        print(f"-> {m} ...", flush=True)
        results.append(await time_one(client, m))
    print("\n=== results ===")
    for model, elapsed, tokens, status in results:
        rate = tokens / elapsed if elapsed > 0 and tokens else 0
        print(f"  {model:24s} {elapsed:6.1f}s  {tokens:5d} tok  {rate:5.2f} tok/s  {status}")
    await client.aclose()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
