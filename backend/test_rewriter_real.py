"""Run the actual rewriter prompt (with the same critic report) to see
what JSON shape the model actually emits."""
import asyncio
import os
import sys
import time
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.services.llm.client import (  # noqa: E402
    LLMClient,
    LLMMessage,
    LLMRequest,
)


async def main() -> int:
    base_url = os.environ.get("LLM_BASE_URL", "https://your-provider.example/v1")
    api_key = os.environ.get("LLM_API_KEY", "your-api-key-here")

    prompt = (
        "你是玄幻长篇小说的改稿编辑。\n"
        "请根据审核报告对第 1 章做定向修改。\n\n"
        "【草稿】\n"
        "林萧被逐出山门后, 走在泥泞的山路上。他想到过去三年的屈辱, 心中燃起复仇之火。\n"
        "雨越下越大, 他躲进一个破庙里。庙里供奉着一尊破碎的神像, 神像的眼珠似乎在盯着他。\n\n"
        "【审核报告】\n"
        '{"total": 65, "scores": {"plot_continuity": 70, "writing_quality": 60, "rhythm": 65, "foreshadow_density": 60}, '
        '"issues": [{"category": "rhythm", "severity": "high", "quote": "雨越下越大", '
        '"comment": "节奏太急, 建议加一段内心独白展开心境"}]}\n\n'
        "【细节约束】\n"
        "(无)\n\n"
        "请输出严格 JSON：\n"
        "{\n"
        '  "rewritten_content": "...",\n'
        '  "changes": [\n'
        '    {"section": "段首/中段/段尾", "before": "...", "after": "...", "reason": "..."}\n'
        "  ],\n"
        '  "preserved": ["本章保留不动的元素"]\n'
        "}\n"
        "注意只改正文中与 issues 直接相关的内容, 其他段落保持原貌。"
    )

    client = LLMClient()
    req = LLMRequest(
        model="step-3.7-flash",
        max_tokens=5500,
        temperature=0.0,
        response_format={"type": "json_object"},
        messages=[LLMMessage(role="user", content=prompt)],
    )
    t0 = time.perf_counter()
    try:
        result = await client.chat(base_url=base_url, api_key=api_key, request=req)
        elapsed = time.perf_counter() - t0
        print(f"OK in {elapsed:.1f}s, in={result.input_tokens} out={result.output_tokens}")
        with open("rewriter_response.txt", "w", encoding="utf-8") as f:
            f.write(result.content)
        print(f"content length: {len(result.content)}")
        # parse it
        try:
            obj = json.loads(result.content)
            print(f"keys: {list(obj.keys())}")
        except Exception as e:
            print(f"json.loads failed: {e}")
    except Exception as exc:
        elapsed = time.perf_counter() - t0
        print(f"FAIL in {elapsed:.1f}s: {type(exc).__name__}: {exc!r}")
        return 1
    finally:
        await client.aclose()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
