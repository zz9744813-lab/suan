"""Test 4000-token Draft-style generation timing on the real provider."""
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
    model = "deepseek-v4-flash"

    client = LLMClient()
    # Use the actual planner prompt to force a real 2-4K token reply
    req = LLMRequest(
        model=model,
        max_tokens=4000,
        temperature=0.8,
        messages=[
            LLMMessage(role="user", content=(
                "你是玄幻长篇小说《山门被逐》的正文写手。\n"
                "第 1 章，标题：山门被逐\n"
                "目标字数：3000 字\n\n"
                "【规划】\n"
                "林萧因丹田被废，从玄阳宗外门被逐出山门。\n"
                "三个节拍：日常铺垫 / 冲突爆发 / 被逐山门。\n\n"
                "请直接输出 3000 字左右的中文小说正文，不要解释，不要 JSON 包装。"
            )),
        ],
    )

    t0 = time.perf_counter()
    try:
        result = await client.chat(base_url=base_url, api_key=api_key, request=req)
        elapsed = time.perf_counter() - t0
        print(f"\nOK in {elapsed:.1f}s")
        print(f"tokens: in={result.input_tokens} out={result.output_tokens}")
        rate = result.output_tokens / elapsed if elapsed > 0 else 0
        print(f"rate: {rate:.2f} tok/s")
        print(f"content length: {len(result.content)} chars")
        print(f"content (first 300): {result.content[:300]!r}")
        return 0
    except Exception as exc:
        elapsed = time.perf_counter() - t0
        print(f"\nFAIL in {elapsed:.1f}s: {type(exc).__name__}: {exc!r}")
        return 1
    finally:
        await client.aclose()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
