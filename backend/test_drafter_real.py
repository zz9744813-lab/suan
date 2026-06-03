"""Run the actual drafter prompt and dump both content and reasoning_content."""
import asyncio
import os
import sys
import time
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.core.database import AsyncSessionLocal
from app.services.llm.client import (  # noqa: E402
    LLMClient,
    LLMMessage,
    LLMRequest,
)
from app.services.prompt_engine import PromptEngine  # noqa: E402


async def main() -> int:
    base_url = os.environ.get("LLM_BASE_URL", "https://your-provider.example/v1")
    api_key = os.environ.get("LLM_API_KEY", "your-api-key-here")

    inputs = {
        "chapter_no": 1,
        "title": "山门被逐",
        "target_word_count": 3000,
        "chapter_plan": json.dumps({
            "goal": "林萧被逐出山门",
            "conflict": "丹田被废，被迫离开",
            "beats": [
                {"name": "开场", "summary": "清晨，山门外，雨中", "characters": ["林萧"]},
                {"name": "冲突", "summary": "宗门宣布逐出", "characters": ["林萧", "管事"]},
                {"name": "离山", "summary": "林萧独自走入雨夜", "characters": ["林萧"]},
            ],
            "hook": "林萧听到身后有脚步声想要跟出来，又停住了。",
        }, ensure_ascii=False),
        "memory_context": "[]",
        "detail_constraints": "(无)",
        "behavior_patterns": "(暂无)",
        "style_guide": "稿纸感中文，段间留白，对话短而有情绪。",
        "user_preferences": "(暂无)",
    }
    async with AsyncSessionLocal() as db:
        engine = PromptEngine()
        rendered = await engine.render(db, "drafter_main", inputs)
        prompt = rendered.body

    client = LLMClient()
    req = LLMRequest(
        model="step-3.7-flash",
        max_tokens=5000,
        temperature=0.9,
        messages=[LLMMessage(role="user", content=prompt)],
    )
    t0 = time.perf_counter()
    try:
        result = await client.chat(base_url=base_url, api_key=api_key, request=req)
        elapsed = time.perf_counter() - t0
        print(f"OK in {elapsed:.1f}s, in={result.input_tokens} out={result.output_tokens}")
        # dump raw response so we can see both content and reasoning_content
        raw = result.raw
        msg = (raw.get("choices") or [{}])[0].get("message") or {}
        print(f"raw keys: {list(raw.keys())}")
        print(f"message keys: {list(msg.keys())}")
        print(f"content len: {len(msg.get('content') or '')}")
        print(f"reasoning_content len: {len(msg.get('reasoning_content') or '')}")
        print(f"\n--- content (first 300) ---")
        print((msg.get("content") or "")[:300])
        print(f"\n--- reasoning_content (first 300) ---")
        print((msg.get("reasoning_content") or "")[:300])
        print(f"\n--- result.content (first 300) ---")
        print(result.content[:300])
        with open("drafter_response.txt", "w", encoding="utf-8") as f:
            f.write(f"--- content ---\n{msg.get('content') or ''}\n\n")
            f.write(f"--- reasoning_content ---\n{msg.get('reasoning_content') or ''}\n\n")
            f.write(f"--- result.content (picked) ---\n{result.content}\n")
        print("wrote drafter_response.txt")
    except Exception as exc:
        elapsed = time.perf_counter() - t0
        print(f"FAIL in {elapsed:.1f}s: {type(exc).__name__}: {exc!r}")
        return 1
    finally:
        await client.aclose()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
