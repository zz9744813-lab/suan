"""Verify step-3.7-flash output quality (no <think> preamble)."""
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


async def main() -> int:
    base_url = os.environ.get("LLM_BASE_URL", "https://your-provider.example/v1")
    api_key = os.environ.get("LLM_API_KEY", "your-api-key-here")

    client = LLMClient()
    req = LLMRequest(
        model="step-3.7-flash",
        max_tokens=2000,
        temperature=0.7,
        messages=[
            LLMMessage(role="user", content=(
                "你是玄幻长篇小说《山门被逐》的章节规划师。\n"
                "第 1 章，标题：山门被逐\n"
                "目标字数：3000\n\n"
                "【大纲】\n林萧因丹田被废，从玄阳宗外门被逐出山门。\n\n"
                "请输出严格的 JSON 规划：\n"
                '{"goal": "...", "conflict": "...", "beats": [...], "hook": "..."}'
            )),
        ],
    )
    t0 = time.perf_counter()
    try:
        result = await client.chat(base_url=base_url, api_key=api_key, request=req)
        elapsed = time.perf_counter() - t0
        print(f"OK in {elapsed:.1f}s, in={result.input_tokens} out={result.output_tokens}")
        content = result.content
        print(f"content length: {len(content)} chars")
        print(f"first 600 chars:\n{content[:600]}")
        print(f"\nstarts with JSON? {content.lstrip().startswith('{')}")
        print(f"contains <think>? {'<think>' in content.lower()}")
    except Exception as exc:
        elapsed = time.perf_counter() - t0
        print(f"FAIL in {elapsed:.1f}s: {type(exc).__name__}: {exc!r}")
        return 1
    finally:
        await client.aclose()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
