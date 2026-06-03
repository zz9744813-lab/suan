"""Direct API perf probe: streaming vs non-streaming at various max_tokens.

Goal: understand (1) how total time scales with max_tokens, (2) how much
savings streaming gives on TTFT, (3) whether the model can actually fill
large max_tokens on this provider.

Provider: whitedream step-3.7-flash (real, used by the pipeline).
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from typing import Any

sys.stdout.reconfigure(encoding="utf-8")

import httpx

BASE_URL = "https://sub.whitedream.top/v1"
MODEL = "step-3.7-flash"


def _load_whitedream_key() -> str:
    """Pull the real whitedream API key from the DB so the probe hits
    the same provider the pipeline does. Falls back to a hard-coded
    literal only for offline dev."""
    import os, sqlite3
    here = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(here, "data", "novelforge.db"),
        os.path.join(here, "novelforge.db"),
    ]
    for path in candidates:
        if os.path.exists(path):
            c = sqlite3.connect(path)
            row = c.execute(
                "SELECT api_key FROM model_providers WHERE name='whitedream' AND enabled=1"
            ).fetchone()
            c.close()
            if row and row[0]:
                return row[0]
    raise SystemExit(f"whitedream key not found in {candidates}")


API_KEY = _load_whitedream_key()

# Same prompt for all runs (just a writing task)
PROMPT = (
    "请用玄幻网文风格写一段约 N 字的场景，主角林萧在山门外被废丹田后，"
    "独自走入雨夜。场景要包含环境描写、心理活动、一句对话，章末留一个钩子。"
    "不要写元说明。"
)


async def call_non_streaming(client: httpx.AsyncClient, max_tokens: int) -> dict:
    t0 = time.perf_counter()
    try:
        resp = await client.post(
            "/chat/completions",
            headers={"Authorization": f"Bearer {API_KEY}"},
            json={
                "model": MODEL,
                "messages": [{"role": "user", "content": PROMPT.replace("N", str(max_tokens))}],
                "temperature": 0.9,
                "max_tokens": max_tokens,
                "extra_body": {"reasoning_effort": "low"},
            },
            timeout=600.0,
        )
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}", "elapsed_s": time.perf_counter() - t0}

    elapsed = time.perf_counter() - t0
    if resp.status_code != 200:
        return {"error": f"HTTP {resp.status_code}: {resp.text[:200]}", "elapsed_s": elapsed}

    data = resp.json()
    msg = (data.get("choices") or [{}])[0].get("message") or {}
    usage = data.get("usage") or {}
    content = msg.get("content") or ""
    reasoning = msg.get("reasoning_content") or ""
    return {
        "elapsed_s": elapsed,
        "http_status": resp.status_code,
        "input_tokens": usage.get("prompt_tokens"),
        "output_tokens": usage.get("completion_tokens"),
        "content_chars": len(content),
        "reasoning_chars": len(reasoning),
        "content_first_100": content[:100],
    }


async def call_streaming(client: httpx.AsyncClient, max_tokens: int) -> dict:
    t0 = time.perf_counter()
    ttft = None
    chunks: list[str] = []
    reasoning_chunks: list[str] = []
    try:
        async with client.stream(
            "POST",
            "/chat/completions",
            headers={"Authorization": f"Bearer {API_KEY}"},
            json={
                "model": MODEL,
                "messages": [{"role": "user", "content": PROMPT.replace("N", str(max_tokens))}],
                "temperature": 0.9,
                "max_tokens": max_tokens,
                "stream": True,
                "stream_options": {"include_usage": True},
                "extra_body": {"reasoning_effort": "low"},
            },
            timeout=600.0,
        ) as resp:
            if resp.status_code != 200:
                body = await resp.aread()
                return {"error": f"HTTP {resp.status_code}: {body[:200].decode('utf-8', 'ignore')}", "elapsed_s": time.perf_counter() - t0}
            async for line in resp.aiter_lines():
                if not line or not line.startswith("data: "):
                    continue
                payload = line[6:].strip()
                if payload == "[DONE]":
                    break
                try:
                    evt = json.loads(payload)
                except json.JSONDecodeError:
                    continue
                choice = (evt.get("choices") or [{}])[0]
                delta = choice.get("delta") or {}
                content = delta.get("content") or ""
                reasoning = delta.get("reasoning_content") or ""
                if content or reasoning:
                    if ttft is None:
                        ttft = time.perf_counter() - t0
                if content:
                    chunks.append(content)
                if reasoning:
                    reasoning_chunks.append(reasoning)
                # usage event (last chunk with usage)
                if not choice and evt.get("usage"):
                    usage = evt["usage"]
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}", "elapsed_s": time.perf_counter() - t0}

    elapsed = time.perf_counter() - t0
    content = "".join(chunks)
    reasoning = "".join(reasoning_chunks)
    return {
        "elapsed_s": elapsed,
        "ttft_s": ttft,
        "content_chars": len(content),
        "reasoning_chars": len(reasoning),
        "content_first_100": content[:100],
    }


async def main():
    print(f"=== Provider: {BASE_URL}  Model: {MODEL} ===\n")
    limits = [500, 1000, 2000, 4000, 8000]
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=600.0) as client:
        # non-streaming
        print("=" * 80)
        print("NON-STREAMING")
        print("=" * 80)
        for n in limits:
            print(f"\n--- max_tokens={n} ---")
            r = await call_non_streaming(client, n)
            if "error" in r:
                print(f"  ERROR: {r['error']}  ({r.get('elapsed_s', 0):.1f}s)")
                continue
            print(f"  elapsed:      {r['elapsed_s']:.2f}s")
            print(f"  in_tok/out_tok: {r['input_tokens']}/{r['output_tokens']}")
            print(f"  content chars:  {r['content_chars']}  reasoning chars: {r['reasoning_chars']}")
            print(f"  first 100:      {r['content_first_100']!r}")
            await asyncio.sleep(2)

        # streaming
        print()
        print("=" * 80)
        print("STREAMING")
        print("=" * 80)
        for n in limits:
            print(f"\n--- max_tokens={n} ---")
            r = await call_streaming(client, n)
            if "error" in r:
                print(f"  ERROR: {r['error']}  ({r.get('elapsed_s', 0):.1f}s)")
                continue
            print(f"  elapsed:        {r['elapsed_s']:.2f}s")
            print(f"  TTFT:           {r.get('ttft_s', 0):.3f}s" if r.get('ttft_s') is not None else "  TTFT:           (none)")
            print(f"  content chars:  {r['content_chars']}  reasoning chars: {r['reasoning_chars']}")
            print(f"  first 100:      {r['content_first_100']!r}")
            await asyncio.sleep(2)


if __name__ == "__main__":
    asyncio.run(main())
