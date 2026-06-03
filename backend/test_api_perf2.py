"""R15 / input×output perf probe.

Vary BOTH input length and max_tokens, for both streaming and
non-streaming. Goal: confirm the model handles large-prompt + large-
output combos within a reasonable time budget, and characterize the
"input length → first-byte delay" relationship the previous probe
didn't touch.

Sizes:
  input  ≈ 100 / 1000 / 4000 / 8000 tokens
  output max_tokens  2000 / 6000
  stream  on / off

Each cell: 1 run (the user cares about quality, not statistical rigour).
Total runs: 4 × 2 × 2 = 16.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time

sys.stdout.reconfigure(encoding="utf-8")

import httpx

BASE_URL = "https://sub.whitedream.top/v1"
MODEL = "step-3.7-flash"


def _load_whitedream_key() -> str:
    import sqlite3
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

# --- Build prompts at 4 input sizes ---
BASE_PROMPT = (
    "请用玄幻网文风格写一段场景，主角林萧在山门外被废丹田后独自走入雨夜。"
    "场景要包含环境描写、心理活动、一句对话，章末留一个钩子。"
    "不要写元说明。"
)
# Chinese ratio: ~1.5 chars per token, so 100 tokens ≈ 150 chars.
# Pad to 1k/4k/8k tokens with meaningless but realistic-looking filler.
FILLER = (
    "（背景设定：本章所属的玄幻世界名为九霄大陆，大陆之上宗门林立，"
    "以剑道为尊。主角林萧出身寒门，父亲早亡，母亲临终前留下一枚暖玉，"
    "玉中藏有远古剑诀的残篇。林萧十六岁入青云宗为外门弟子，资质平平，"
    "但因机缘巧合测出双灵根——金火双灵根，遂被宗门破格录入内门。"
    "然而他入内门后遭到管事与师兄端木燕的嫉恨，后者设计诬陷他偷盗"
    "镇宗之宝雪莲，林萧百口莫辩，被当众废去丹田，逐出山门。"
    "这一章发生在林萧被逐之夜，雨夜山门，山门外只有他一个人。"
    "他需要独自走下三千石阶，走向未知的江湖。"
    "上述设定在写作时不要显式说出，但要用细节体现。"
    "例如：写他抚摸暖玉的动作体现母子情，写他对宗门建筑的最后一眼"
    "体现他对往昔的不舍，写他踏入雨中体现他与过去的决裂。"
    "动作要细、要有节奏、对白要短而有力。整段约五百字左右。）"
)
# Append multiple copies of FILLER to reach 1k/4k/8k tokens.
def make_prompt(target_tokens: int) -> str:
    # Each FILLER is ~250 tokens. Scale.
    n_copies = max(0, (target_tokens - 100) // 250)
    if n_copies == 0:
        return BASE_PROMPT
    return BASE_PROMPT + "\n\n" + (FILLER + "\n") * n_copies


async def call_non_streaming(client: httpx.AsyncClient, prompt: str, max_tokens: int) -> dict:
    t0 = time.perf_counter()
    try:
        resp = await client.post(
            "/chat/completions",
            headers={"Authorization": f"Bearer {API_KEY}"},
            json={
                "model": MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.9,
                "max_tokens": max_tokens,
                "extra_body": {"reasoning_effort": "low"},
            },
            timeout=900.0,
        )
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}", "elapsed_s": time.perf_counter() - t0}
    elapsed = time.perf_counter() - t0
    if resp.status_code != 200:
        return {"error": f"HTTP {resp.status_code}: {resp.text[:200]}", "elapsed_s": elapsed}
    data = resp.json()
    msg = (data.get("choices") or [{}])[0].get("message") or {}
    usage = data.get("usage") or {}
    return {
        "elapsed_s": elapsed,
        "in_tok": usage.get("prompt_tokens"),
        "out_tok": usage.get("completion_tokens"),
        "content_chars": len(msg.get("content") or ""),
        "reasoning_chars": len(msg.get("reasoning_content") or ""),
    }


async def call_streaming(client: httpx.AsyncClient, prompt: str, max_tokens: int) -> dict:
    t0 = time.perf_counter()
    ttft = None
    chunks: list[str] = []
    rchunks: list[str] = []
    usage = None
    try:
        async with client.stream(
            "POST", "/chat/completions",
            headers={"Authorization": f"Bearer {API_KEY}"},
            json={
                "model": MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.9,
                "max_tokens": max_tokens,
                "stream": True,
                "stream_options": {"include_usage": True},
                "extra_body": {"reasoning_effort": "low"},
            },
            timeout=900.0,
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
                c = delta.get("content") or ""
                r = delta.get("reasoning_content") or ""
                if (c or r) and ttft is None:
                    ttft = time.perf_counter() - t0
                if c:
                    chunks.append(c)
                if r:
                    rchunks.append(r)
                if not choice and evt.get("usage"):
                    usage = evt["usage"]
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}", "elapsed_s": time.perf_counter() - t0}
    elapsed = time.perf_counter() - t0
    return {
        "elapsed_s": elapsed,
        "ttft_s": ttft,
        "in_tok": (usage or {}).get("prompt_tokens"),
        "out_tok": (usage or {}).get("completion_tokens"),
        "content_chars": len("".join(chunks)),
        "reasoning_chars": len("".join(rchunks)),
    }


def fmt(r: dict) -> str:
    if "error" in r:
        return f"ERR {r['error'][:50]}  ({r.get('elapsed_s', 0):.1f}s)"
    parts = [f"{r['elapsed_s']:6.1f}s"]
    if "ttft_s" in r and r["ttft_s"] is not None:
        parts.append(f"TTFT {r['ttft_s']:5.2f}s")
    parts.append(f"in/out={r.get('in_tok', '?')}/{r.get('out_tok', '?')}")
    parts.append(f"c/r={r['content_chars']}/{r['reasoning_chars']}")
    return "  ".join(parts)


async def main():
    print(f"=== {BASE_URL}  model={MODEL} ===\n")
    INPUT_SIZES = [100, 1000, 4000, 8000]
    MAX_TOKENS = [2000, 6000]
    results: list[dict] = []

    async with httpx.AsyncClient(base_url=BASE_URL, timeout=900.0) as client:
        for mode in ("non-streaming", "streaming"):
            print("=" * 90)
            print(mode.upper())
            print("=" * 90)
            for it in INPUT_SIZES:
                prompt = make_prompt(it)
                # Measure actual input size
                head_resp = await client.post(
                    "/chat/completions",
                    headers={"Authorization": f"Bearer {API_KEY}"},
                    json={"model": MODEL, "messages": [{"role": "user", "content": prompt}], "max_tokens": 1},
                    timeout=60,
                )
                actual_in = (head_resp.json().get("usage") or {}).get("prompt_tokens")
                print(f"\n--- input ~{it} tokens (actual {actual_in})  prompt chars: {len(prompt)} ---")
                for mt in MAX_TOKENS:
                    if mode == "non-streaming":
                        r = await call_non_streaming(client, prompt, mt)
                    else:
                        r = await call_streaming(client, prompt, mt)
                    r["mode"] = mode
                    r["target_in"] = it
                    r["max_tokens"] = mt
                    r["actual_in"] = actual_in
                    results.append(r)
                    print(f"  max_tok={mt:5d}  {fmt(r)}")
                    await asyncio.sleep(2)

    # Summary table
    print("\n\n=== SUMMARY (elapsed_s) ===")
    print(f"{'mode':<14} {'in_tok':>8} {'max_out':>8} {'elapsed':>8} {'TTFT':>8} {'out_tok':>8} {'c/r':>14}")
    print("-" * 80)
    for r in results:
        if "error" in r:
            print(f"{r['mode']:<14} {r['target_in']:>8} {r['max_tokens']:>8}  ERR {r['error'][:30]}")
            continue
        ttft = f"{r['ttft_s']:.2f}s" if r.get('ttft_s') is not None else "-"
        cr = f"{r['content_chars']}/{r['reasoning_chars']}"
        print(f"{r['mode']:<14} {r.get('actual_in', '?'):>8} {r['max_tokens']:>8} {r['elapsed_s']:>7.1f}s {ttft:>8} {r.get('out_tok', '?'):>8} {cr:>14}")


if __name__ == "__main__":
    asyncio.run(main())
