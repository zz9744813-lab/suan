"""Run the actual planner prompt (rendered for chapter 12) through the
real LLM and dump the full response so we can see why it isn't valid JSON.
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


async def main() -> int:
    base_url = os.environ.get("LLM_BASE_URL", "https://your-provider.example/v1")
    api_key = os.environ.get("LLM_API_KEY", "your-api-key-here")

    with open("actual_planner_prompt.txt", encoding="utf-8") as f:
        prompt = f.read()

    client = LLMClient()
    req = LLMRequest(
        model="step-3.7-flash",
        max_tokens=2000,
        temperature=0.7,
        response_format={"type": "json_object"},
        messages=[LLMMessage(role="user", content=prompt)],
    )
    t0 = time.perf_counter()
    try:
        result = await client.chat(base_url=base_url, api_key=api_key, request=req)
        elapsed = time.perf_counter() - t0
        print(f"OK in {elapsed:.1f}s, in={result.input_tokens} out={result.output_tokens}")
        with open("planner_response.txt", "w", encoding="utf-8") as f:
            f.write(f"--- usage ---\nt")
            f.write(f"tokens: {result.input_tokens}/{result.output_tokens}, "
                    f"cost=${result.cost_usd}, latency={result.duration_ms}ms\n")
            f.write(f"--- content (utf-8) ---\n")
            f.write(result.content)
        print(f"wrote {len(result.content)} chars to planner_response.txt")
        print(f"starts with {{: {result.content.lstrip().startswith('{')}")
        print(f"first 300: {result.content[:300]!r}")
    except Exception as exc:
        elapsed = time.perf_counter() - t0
        print(f"FAIL in {elapsed:.1f}s: {type(exc).__name__}: {exc!r}")
        return 1
    finally:
        await client.aclose()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
