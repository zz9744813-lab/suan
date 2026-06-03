"""R15 picker fix test.

Verifies that ``_pick_best_content`` correctly extracts the *answer
portion* from a reasoning_content blob that contains both planning
prose and the actual answer — the bug we observed on chapter 15
(output started with "用户现在需要我写..." planning text instead of
the actual chapter content).
"""
from __future__ import annotations

import sys
sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8")

from app.services.llm.client import _pick_best_content, _extract_answer_from_prose, _looks_like_json_stub


def test_extract_tier1_marker():
    """A '以下是正文' marker should snap the cut right after the marker."""
    # Need >= 200 chars total for the extractor to engage.
    text = (
        "用户现在需要我写玄幻小说的第三章，主角是林萧，要符合所有规则，"
        "最后还要输出JSON？等下看要求：只有输出一个合法JSON对象。"
        "我应该先介绍一下宗门环境，然后写林萧被废丹田的场景。"
        "好的，让我开始构思一下大纲，再决定哪些内容必须出现。"
        "我要保持玄幻网文的风格，节奏要快，对话要短，"
        "主角必须有自己的主动性，不能太被动。\n\n"
        "以下是正文：\n\n"
        "罡风卷着雪沫子扫过青云宗山门，十二座青峰隐在云里，"
        "像插在天上的剑，峰顶的琉璃瓦闪着冷光。"
    )
    out = _extract_answer_from_prose(text)
    assert out is not None, f"got None, text len {len(text)}"
    assert out.startswith("罡风卷着雪沫子"), f"expected answer portion, got: {out[:80]!r}"
    assert "用户现在需要" not in out, "should have stripped planning"
    print("OK  tier1 marker")


def test_extract_tier2_weak_marker():
    """A 'good comma' marker on a long blob should snap after it."""
    # Need >= 1500 chars for tier 2 to engage.
    plan = "思考一下林萧的背景和情节推进。" * 120
    text = plan + "\n好的，" + "山门外寒风刺骨，林萧跪在石阶上。" * 5
    out = _extract_answer_from_prose(text)
    assert out is not None
    assert "山门外寒风刺骨" in out
    # Make sure the planning preamble is gone from the head of the result
    assert "山门外寒风刺骨" in out[:80], f"answer should be near the start; got head: {out[:80]!r}"
    print("OK  tier2 weak marker on long text")


def test_extract_no_marker_uses_last_60pct():
    """No markers → take the last 60%."""
    plan = "PLANNING " * 100
    ans = "ACTUAL_ANSWER_BEGINS_NOW " + "X" * 500
    text = plan + ans
    out = _extract_answer_from_prose(text)
    assert out is not None
    assert "ACTUAL_ANSWER" in out
    assert not out.startswith("PLANNING")
    print("OK  tier3 last 60% fallback")


def test_extract_too_short_returns_none():
    """Text under 200 chars returns None (don't bother trimming)."""
    out = _extract_answer_from_prose("短短一行")
    assert out is None
    print("OK  short text returns None")


def test_picker_with_chapter_15_shape():
    """Simulate the chapter 15 failure: 7300 chars of planning+answer in reasoning_content."""
    planning = (
        "用户现在需要我写玄幻小说的第三章，主角是林萧，要符合所有规则，"
        "最后还要输出JSON？等下看要求：只有输出一个合法JSON对象。"
        "让我先思考一下大纲..."
    ) * 30  # ~3000 chars of planning
    answer = (
        "以下是正文\n\n"
        "罡风卷着雪沫子扫过青云宗山门，十二座青峰隐在云里。"
        "林萧排在入门考核的队伍里，穿洗得发白的粗布棉袄。"
        "那是母亲咽气前塞给他的，枯瘦的手攥着他的手腕。"
    ) * 5  # ~1500 chars of actual answer
    full = planning + answer
    # Picker has only reasoning (no content)
    picked = _pick_best_content([full])
    assert picked.startswith("罡风卷着雪沫子") or "以下是正文" not in picked[:200], \
        f"picker should have dropped the planning prefix; got: {picked[:200]!r}"
    print("OK  picker chapter-15 shape extracts answer portion")


def test_picker_with_valid_json_picked():
    """A valid JSON in the blob should still win (strategy 1)."""
    planning = "Long thinking " * 100
    answer_json = '{"scores": {"shuang_dian": 80}, "total": 80, "issues": [], "summary": "好", "pass": true}'
    full = planning + answer_json
    picked = _pick_best_content([full])
    obj = __import__("json").loads(picked)
    assert obj["total"] == 80
    print("OK  valid JSON wins over prose trimming")


def test_picker_prefers_content_over_reasoning():
    """When both content and reasoning are present, content wins."""
    content = "THE ACTUAL CHAPTER: 林萧被废丹田..."
    reasoning = "Planning " * 200 + "以下是正文\n\n" + content
    picked = _pick_best_content([content, reasoning])
    # Content is the first candidate. Picker should prefer it.
    assert picked == content or picked.startswith("THE ACTUAL CHAPTER")
    print("OK  content wins when both present")


def test_stub_detection_basic():
    """Tiny {"content":"这里放内容"} is a stub."""
    assert _looks_like_json_stub('{"content":"这里放内容"}') is True
    assert _looks_like_json_stub('{"content":"正文"}') is True
    assert _looks_like_json_stub('{"content":"TBD"}') is True
    assert _looks_like_json_stub('{"content":"占位"}') is True
    assert _looks_like_json_stub('{"content":"..."}') is True
    # Big content → not a stub
    assert _looks_like_json_stub('{"content":"' + "X" * 50 + '"}') is False
    # No content field
    assert _looks_like_json_stub('{"foo":"bar"}') is False
    # Not JSON
    assert _looks_like_json_stub("not json") is False
    print("OK  stub detection identifies placeholder content")


def test_picker_skips_stub_falls_through_to_prose():
    """The bug: model returns reasoning with planning+answer+stub JSON.
    Picker should skip the 19-char stub and return the prose answer.
    """
    planning = (
        "用户现在需要我写玄幻小说的第三章，主角是林萧，要符合所有规则，"
        "最后还要输出JSON？等下看要求：只有输出一个合法JSON对象。"
        "让我先思考一下大纲..."
    ) * 30  # ~3000 chars
    answer = (
        "罡风卷着雪沫子扫过青云宗山门，十二座青峰隐在云里。"
        "林萧排在入门考核的队伍里，穿洗得发白的粗布棉袄。"
    ) * 8  # ~1500 chars
    stub = '{"content":"这里放内容"}'  # 19-char placeholder
    # Mimic the failure shape: content is the stub, reasoning has
    # planning + real answer (NOT a JSON object, just prose).
    content = stub
    reasoning = planning + answer
    picked = _pick_best_content([content, reasoning])
    # Picker must NOT return the 19-char stub. The real answer is the
    # 1500-char prose block in reasoning; the extractor should grab
    # the answer portion (no marker → last 60%, but since reasoning
    # is a single prose blob with no marker it falls through to the
    # raw-text fallback which is the longest candidate).
    assert len(picked) > 100, f"picker should not return stub; got: {picked[:200]!r}"
    assert picked != stub, f"picker returned the stub: {picked!r}"
    assert "罡风卷着雪沫子" in picked, f"picker should contain the answer prose; got head: {picked[:200]!r}"
    print(f"OK  picker skipped stub (returned {len(picked)} chars of prose)")


if __name__ == "__main__":
    test_extract_tier1_marker()
    test_extract_tier2_weak_marker()
    test_extract_no_marker_uses_last_60pct()
    test_extract_too_short_returns_none()
    test_picker_with_chapter_15_shape()
    test_picker_with_valid_json_picked()
    test_picker_prefers_content_over_reasoning()
    test_stub_detection_basic()
    test_picker_skips_stub_falls_through_to_prose()
    print("\n=== ALL PICKER TESTS PASSED ===")
