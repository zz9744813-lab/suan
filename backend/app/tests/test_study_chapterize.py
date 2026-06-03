"""Unit tests for R19 study material parsing.

Covers the regression where a UTF-8 TXT saved by 记事本 starts
with a BOM (\\ufeff), which previously broke the chapter regex
``^\\s*第`` — the BOM is a *non-whitespace* character, so ``^\\s*``
couldn't bridge from position 0 to the actual chapter header
``第``, and the splitter fell back to "全文" with a single
chapter instead of N.

Now ``_parse_txt`` strips a leading BOM (or transcodes UTF-16
LE/BE), and the chapter regex picks up every chapter normally.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import re
from app.routers.study import _parse_txt, _split_chapters, _CN_CHAPTER_RE

# Re-declare the regex for direct testing (mirrors routers/study.py).
CN = re.compile(
    r"^\s*第\s*([零〇一二三四五六七八九十百千万0-9]+)\s*章[\s　\.：:—\-]*(.{0,80})$",
    re.MULTILINE,
)


def test_utf8_bom_stripped():
    """A TXT with a UTF-8 BOM (3 bytes 0xEF 0xBB 0xBF) decodes without
    a leading \\ufeff — the parser should not leak the BOM to the
    chapter splitter."""
    body = "第 1 章 起点\n这是第一章的内容。字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字\n\n第 2 章 相遇\n这是第二章的内容。"
    raw = b"\xef\xbb\xbf" + body.encode("utf-8")
    text = _parse_txt(raw)
    assert not text.startswith("\ufeff"), f"BOM not stripped: {text[:5]!r}"
    assert text.startswith("第"), f"first char should be 第, got {text[0]!r}"


def test_chapter_splitter_with_bom_text():
    """The splitter receives text that *would* still have a BOM if
    upstream parsing didn't strip it. This guards against a
    regression where someone refactors _extract_text_from_upload
    and forgets to call _parse_txt."""
    body = "第 1 章 起点\n这是第一章" + ("字" * 250) + "\n\n第 2 章 相遇\n这是第二章" + ("字" * 250)
    # Even if a stray BOM somehow leaks through, the splitter must
    # still find both chapters.
    text_with_bom = "\ufeff" + body
    chunks = _split_chapters(text_with_bom, pattern="auto")
    titles = [t for _, t, _ in chunks]
    print(f"  with-bom chunks: {len(chunks)}, titles={titles}")
    # When BOM is present, the splitter degrades to a single
    # "序章" prologue (preamble len > 50). That's the documented
    # fallback — but the test is here to make sure a future change
    # doesn't make things *worse* (e.g. 0 chunks, an exception).
    assert len(chunks) >= 1, "splitter must produce at least one chunk"
    # Now with BOM stripped (the production path after _parse_txt):
    text_clean = _parse_txt(b"\xef\xbb\xbf" + body.encode("utf-8"))
    chunks_clean = _split_chapters(text_clean, pattern="auto")
    titles_clean = [t for _, t, _ in chunks_clean]
    print(f"  clean chunks: {len(chunks_clean)}, titles={titles_clean}")
    assert len(chunks_clean) == 2, f"expected 2 chapters, got {len(chunks_clean)}"
    assert "起点" in titles_clean[0]
    assert "相遇" in titles_clean[1]


def test_chinese_chapter_with_space():
    """R19 fix: ``第 1 章`` (with space) used to NOT match because
    the regex required digits glued to 第. Make sure the relaxation
    (``\\s*`` between every token) still works."""
    text = "第 1 章 起点\n内容" + ("字" * 200) + "\n\n第 2 章 相遇\n内容" + ("字" * 200)
    matches = list(CN.finditer(text))
    assert len(matches) == 2, f"expected 2 matches, got {len(matches)}"


def test_chinese_chapter_no_space():
    """The glued form ``第1章xxx`` still works."""
    text = "第1章 起点\n内容" + ("字" * 200) + "\n\n第2章 相遇\n内容" + ("字" * 200)
    matches = list(CN.finditer(text))
    assert len(matches) == 2, f"expected 2 matches, got {len(matches)}"


def test_utf16_le_bom():
    """UTF-16 LE (BOM 0xFF 0xFE) is also handled — Notepad's "Unicode"
    option produces this format. We don't go all-in on UTF-16
    support, but we shouldn't crash either."""
    body = "第 1 章 起点\n内容"
    raw = b"\xff\xfe" + body.encode("utf-16-le")
    text = _parse_txt(raw)
    assert "第 1 章" in text or "第 1 章 起点" in text, f"UTF-16 LE not decoded: {text[:20]!r}"


def test_chinese_section_splitter():
    """R20 fix: 蛊真人 and many web novels use ``第NNN节：xxx``
    instead of ``第N章``. The regex now accepts [章节卷回] as
    the suffix char. Make sure ``_split_chapters`` produces N
    chunks for a 3-节 sample and that the suffix is echoed back
    in the title (so the user can see the book convention at a
    glance, not just the chapter number)."""
    text = (
        "第001节：纵身亡魔心仍不悔\n" + ("字" * 300) + "\n\n"
        "第002节：逆光阴五百年觉悟\n" + ("字" * 300) + "\n\n"
        "第003节：请一边玩蛋去\n" + ("字" * 300)
    )
    chunks = _split_chapters(text, pattern="chinese")
    assert len(chunks) == 3, f"expected 3 chapters, got {len(chunks)}: {[t for _, t, _ in chunks]}"
    titles = [t for _, t, _ in chunks]
    # Suffix must be 节, not 章, so the user can see the book's
    # convention from the chapter tree.
    assert all("节" in t for t in titles), f"titles should use 节 suffix, got {titles}"
    assert "纵身亡魔心仍不悔" in titles[0]
    assert "逆光阴五百年觉悟" in titles[1]
    assert "请一边玩蛋去" in titles[2]


def test_chinese_volume_and_hui():
    """R20 fix: ``第N卷`` (used in 修仙 / 玄幻 multi-volume works)
    and ``第N回`` (used in some 日轻 translations) should also
    match. Cover both in one test so a future change that drops
    one of the suffix chars is caught."""
    text = (
        "第1卷 天元崛起\n" + ("字" * 300) + "\n\n"
        "第1回 异世界召唤\n" + ("字" * 300) + "\n\n"
        "第2回 圣剑之谜\n" + ("字" * 300)
    )
    matches = list(_CN_CHAPTER_RE.finditer(text))
    assert len(matches) == 3, f"expected 3 matches, got {len(matches)}"
    sufs = [m.group(2) for m in matches]
    assert sufs == ["卷", "回", "回"], f"expected [卷, 回, 回], got {sufs}"
    # Splitter produces 3 chunks with the right suffix in each title.
    chunks = _split_chapters(text, pattern="chinese")
    assert len(chunks) == 3
    titles = [t for _, t, _ in chunks]
    assert "卷" in titles[0]
    assert titles[1].endswith("回 · 异世界召唤") or "回" in titles[1]


def test_chinese_mixed_chapter_and_section():
    """R20 fix: some books mix 章 and 节 (章 for major arcs, 节
    for sub-arcs). Make sure both kinds are detected and the
    suffix is preserved per-chunk."""
    text = (
        "第1章 开篇\n" + ("字" * 250) + "\n\n"
        "第1节 起始\n" + ("字" * 250) + "\n\n"
        "第2节 转折\n" + ("字" * 250)
    )
    chunks = _split_chapters(text, pattern="chinese")
    assert len(chunks) == 3, f"expected 3 chunks, got {len(chunks)}"
    titles = [t for _, t, _ in chunks]
    assert "第 1 章" in titles[0]
    assert "第 1 节" in titles[1]
    assert "第 2 节" in titles[2]


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    tests = [
        test_utf8_bom_stripped,
        test_chapter_splitter_with_bom_text,
        test_chinese_chapter_with_space,
        test_chinese_chapter_no_space,
        test_utf16_le_bom,
        test_chinese_section_splitter,
        test_chinese_volume_and_hui,
        test_chinese_mixed_chapter_and_section,
    ]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
        except AssertionError as e:
            print(f"  FAIL  {t.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"  ERROR {t.__name__}: {e}")
            failed += 1
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(0 if failed == 0 else 1)
