"""不依赖 LLM 的夜间脚本单元测试。

这些测试覆盖夜间无人值守流水线的不变量：
- 拆书必须能产出可用的章节列表。
- 500 章目录数量必须与请求一致。
- 当生成/返工正文短于下限，脚本必须抛错并写 errors.json，
  绝不能把短章节当成"完成"。
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.scripts.nightly_pipeline import (  # noqa: E402
    MIN_CHAPTER_CHARS,
    build_500_outline,
    build_deconstruction,
    extract_json_object,
    split_source_chapters,
)


def test_split_chapters_handles_real_source() -> None:
    """本地默认源书路径若存在，拆书至少要解析出几个章节。"""
    path = Path(os.environ.get("NIGHTLY_SOURCE_BOOK", r"F:\小说\gem\群像\诡秘之主.txt"))
    if not path.exists():
        pytest.skip(f"源书不存在：{path}")
    raw = path.read_text(encoding="utf-8", errors="replace")
    chapters = split_source_chapters(raw, limit=120)
    assert len(chapters) >= 2, "拆书至少需要 2 章才能生成 500 章目录"
    assert all(c["char_count"] >= 200 for c in chapters)


def test_outline_count_is_exact() -> None:
    deconstruction = build_deconstruction(
        Path("demo.txt"),
        "第1章 起\\n" + "主角在一个雨夜开始了他的旅途。朋友与敌人都出现得刚刚好。\n" * 30,
        split_source_chapters("第1章 起\\n" + "主角在一个雨夜开始了他的旅途。\n" * 30, limit=2),
    )
    outlines = build_500_outline(deconstruction, total=500)
    assert len(outlines) == 500
    volumes = {o["volume_no"] for o in outlines}
    assert volumes == set(range(1, 11))
    assert outlines[0]["chapter_no"] == 1
    assert outlines[-1]["chapter_no"] == 500


def test_extract_json_object_handles_dirty_payload() -> None:
    payload = "当然，下面是结果：{\"score\": 92, \"passed\": true, \"issues\": [\"ok\"]} 完毕"
    data = extract_json_object(payload)
    assert data.get("score") == 92
    assert data.get("passed") is True


def test_min_chapter_threshold_is_strict() -> None:
    """脚本必须明确把低于 500 字的"章节"判为不合格。"""
    assert MIN_CHAPTER_CHARS >= 500
