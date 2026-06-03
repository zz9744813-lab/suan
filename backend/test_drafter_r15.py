"""R15 smoke test: render drafter prompt with NEW behavior_patterns + 玄幻 hard rules.

Compares the actual prompt that gets sent to the LLM against the v1 prompt
(without behavior_patterns lookup) so we can eyeball the new injection
landed correctly.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")

from app.core.database import AsyncSessionLocal, init_db
from app.workers.pipeline import _query_behavior_patterns_for_chapter
from app.services.prompt_engine import PromptEngine


async def main() -> int:
    await init_db()
    base_url = os.environ.get("LLM_BASE_URL", "https://your-provider.example/v1")
    api_key = os.environ.get("LLM_API_KEY", "your-api-key-here")

    # Simulate ctx_data.characters_present
    chars_present = [
        {"name": "林萧", "role": "主角", "tags": ["热血", "隐忍"], "aliases": []},
        {"name": "苏瑶", "role": "女主", "tags": ["青梅"], "aliases": []},
        {"name": "端木燕", "role": "反派", "tags": ["腹黑"], "aliases": []},
    ]

    async with AsyncSessionLocal() as db:
        bp_text = await _query_behavior_patterns_for_chapter(
            db, characters_present=chars_present,
        )
        engine = PromptEngine()
        inputs = {
            "chapter_no": 1,
            "title": "山门被逐",
            "target_word_count": 3000,
            "min_word_count": 2800,
            "max_word_count": 3200,
            "chapter_plan": json.dumps(
                {
                    "goal": "林萧被诬陷偷雪莲，丹田被废，逐出山门",
                    "conflict": "林萧 vs 宗门管事 + 端木燕",
                    "beats": [
                        {"name": "开场·雨中", "summary": "清晨山门外雨，林萧跪在石阶上", "characters": ["林萧"]},
                        {"name": "宣判", "summary": "管事当众宣读罪名，端木燕冷笑", "characters": ["林萧", "管事", "端木燕"]},
                        {"name": "废丹田", "summary": "管事出手废林萧丹田", "characters": ["林萧", "管事"]},
                        {"name": "离山", "summary": "林萧独自走入雨夜，身后有一道身影欲跟又止", "characters": ["林萧", "苏瑶"]},
                    ],
                    "hook": "苏瑶的脚步声响了半步，又硬生生停住。",
                    "foreshadows_to_advance": ["苏瑶对林萧的真实感情"],
                    "foreshadows_to_pay_off": ["雪莲失窃真相"],
                    "must_follow": ["丹田被废必须造成持久影响", "苏瑶未公开表态"],
                    "avoid": ["林萧当场反杀", "苏瑶公开支持林萧"],
                },
                ensure_ascii=False,
            ),
            "memory_context": json.dumps(
                {
                    "characters_present": chars_present,
                    "active_foreshadows": [
                        {"name": "玉佩", "summary": "苏瑶临别塞给林萧的玉佩，疑为母亲遗物"},
                    ],
                    "hard_facts": ["青云宗以剑道立宗", "丹田被废者终生无法修炼"],
                },
                ensure_ascii=False,
            ),
            "detail_constraints": "林萧当前伤势：丹田被废；本章写作必须遵守。\n上一章结尾：（无前章，这是第一章）。本章必须承接。",
            "behavior_patterns": bp_text,
            "style_guide": "稿纸感中文，段间留白，对话短而有情绪。",
            "user_preferences": "(暂无)",
        }
        rendered = await engine.render(db, "drafter_main", inputs)
        prompt = rendered.body
        warnings = rendered.warnings

    # ---- Dump ----
    print(f"=== Rendered prompt length: {len(prompt)} ===")
    print(f"=== Warnings: {warnings} ===")
    print()
    print("=" * 60)
    print(prompt)
    print("=" * 60)
    print()
    # Heuristic checks
    checks = {
        "三段式 段式": "三段式" in prompt,
        "AI 腔 黑名单": "AI 腔" in prompt and "不禁" in prompt,
        "30% 对话占比": "30%" in prompt,
        "字数硬约束": "min_word_count" in prompt and "max_word_count" in prompt,
        "行为模式 实际注入": "行为模式参考" in prompt and "逆境觉醒" in prompt,
        "匹配度 排序": "匹配度" in prompt,
        "对话风格 字段": "对话风格" in prompt,
    }
    print("=== Heuristic checks ===")
    for k, v in checks.items():
        print(f"  {'OK' if v else 'MISS'}  {k}")
    if all(checks.values()):
        print("\n=== ALL PASS ===")
        return 0
    else:
        print("\n=== SOME CHECKS FAILED ===")
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
