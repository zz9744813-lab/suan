"""R19 final E2E test: covers 4-file batch + 2-file mixed batch."""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', line_buffering=True)
sys.path.insert(0, ".")

import os
import shutil
import json
import urllib.request
import urllib.error
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from email.generator import BytesGenerator


BASE = "http://127.0.0.1:8000"

# Track material ids created during this test run so we can
# clean them up at the end. Otherwise the user's "我的书库" page
# gets cluttered with test data: book_1..4, clean, with_bom,
# short. (R23 用户反馈: 「拆书这里又多出一堆你测试用的东西」。
#  用 track-and-cleanup 模式避免再发生。)
_TEST_MATERIAL_IDS: list[int] = []


def make_multipart(files: list[tuple[str, bytes, str]]) -> bytes:
    """Build a multipart/form-data body matching how the
    ``requests`` library / browser would. Returns the raw bytes."""
    boundary = "----NovelForgeR19Boundary"
    parts: list[bytes] = []
    for name, content, filename in files:
        parts.append(f"--{boundary}\r\n".encode())
        parts.append(
            f'Content-Disposition: form-data; name="files"; filename="{filename}"\r\n'.encode()
        )
        parts.append(f"Content-Type: {name}\r\n\r\n".encode())
        parts.append(content)
        parts.append(b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    return b"".join(parts)


def post_multipart(path: str, files: list[tuple[str, bytes, str]]) -> tuple[int, dict]:
    body = make_multipart(files)
    req = urllib.request.Request(
        BASE + path,
        data=body,
        headers={"Content-Type": "multipart/form-data; boundary=----NovelForgeR19Boundary"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8"))


def delete_material(material_id: int) -> None:
    """Delete a material and its chapters / characters / graph
    nodes (cascade). Silently 404s if the material was already
    removed by another test."""
    req = urllib.request.Request(
        f"{BASE}/api/study/materials/{material_id}",
        method="DELETE",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            pass
    except urllib.error.HTTPError:
        pass


def cleanup_test_materials() -> None:
    """Delete all materials this test run created. We use the
    material id range as a filter rather than title name (the
    real bug we hit in R23 was that user-created materials with
    the same title overlap)."""
    for mid in _TEST_MATERIAL_IDS:
        delete_material(mid)
    _TEST_MATERIAL_IDS.clear()


def fmt_result(r: dict) -> str:
    if r.get("ok"):
        m = r["data"]
        return f"  ✓ {m['title']:14s} status={m['status']:6s} chapters={m['chapter_count']}"
    return f"  ✗ {r.get('filename', '?'):14s} error={r.get('error')}"


def make_chapter_body(idx: int) -> bytes:
    return f"第 {idx} 章 第 {idx} 章标题\n".encode("utf-8") + ("字" * 250).encode("utf-8")


def make_short_body() -> bytes:
    # < 200 chars, will be skipped by min_chapter_chars filter
    return "第 1 章 太短\n只有几个字".encode("utf-8")


def test_batch_4_valid():
    print("\n[1] 4 valid TXT files (no BOM):")
    files = [
        ("text/plain", make_chapter_body(i), f"book_{i}.txt")
        for i in range(1, 5)
    ]
    status, body = post_multipart("/api/study/materials/upload/batch", files)
    print(f"  HTTP {status}")
    assert status == 200
    assert body["ok"] is True
    assert len(body["data"]) == 4
    for r in body["data"]:
        assert r["ok"] is True, f"expected success: {r}"
        assert r["data"]["chapter_count"] == 1
        assert r["data"]["status"] == "ready"
        _TEST_MATERIAL_IDS.append(r["data"]["id"])
        print(fmt_result(r))
    print("  PASS")


def test_batch_with_bom():
    print("\n[2] 2 files (1 valid + 1 with UTF-8 BOM + 1 short):")
    valid = make_chapter_body(1)
    with_bom = b"\xef\xbb\xbf" + make_chapter_body(2)
    short = make_short_body()  # < 200 chars, will be skipped
    files = [
        ("text/plain", valid, "clean.txt"),
        ("text/plain", with_bom, "with_bom.txt"),
        ("text/plain", short, "short.txt"),
    ]
    status, body = post_multipart("/api/study/materials/upload/batch", files)
    print(f"  HTTP {status}")
    assert status == 200
    assert body["ok"] is True
    assert len(body["data"]) == 3
    results = body["data"]
    # The 2 long files (clean + with_bom) should both split into 1 chapter
    # each. The "short" file is parsed but its only chapter is < 200 chars
    # so it gets dropped (chapter_count=0, status=draft).
    ok_count = sum(1 for r in results if r["ok"])
    print(f"  ok={ok_count}/3")
    for r in results:
        print(fmt_result(r))
    # All three should parse without error (the short one just yields 0 chapters)
    assert all(r["ok"] for r in results)
    # Track for cleanup.
    for r in results:
        if r.get("data", {}).get("id"):
            _TEST_MATERIAL_IDS.append(r["data"]["id"])
    # The BOM file should still get 1 chapter (BOM stripped by _parse_txt)
    bom_result = next(r for r in results if r["data"]["title"] == "with_bom")
    assert bom_result["data"]["chapter_count"] == 1, f"BOM file not chapterized: {bom_result}"
    print("  PASS — BOM 修复后,带 BOM 的 TXT 也能正确分出 1 章")


def test_batch_oversize():
    print("\n[3] 1 file > 32MB rejected (per-file):")
    big = b"x" * (33 * 1024 * 1024)
    files = [("text/plain", big, "huge.txt")]
    status, body = post_multipart("/api/study/materials/upload/batch", files)
    print(f"  HTTP {status}")
    assert status == 200
    assert body["ok"] is True
    r = body["data"][0]
    assert r["ok"] is False
    assert "过大" in r["error"]
    print(f"  ✓ rejected: {r['error']}")
    print("  PASS")


def test_batch_too_many():
    print("\n[4] 6 files rejected (5-file cap):")
    files = [
        ("text/plain", make_chapter_body(i), f"book_{i}.txt")
        for i in range(1, 7)
    ]
    status, body = post_multipart("/api/study/materials/upload/batch", files)
    print(f"  HTTP {status}")
    assert status == 400
    assert body["ok"] is False
    err = body["error"]["message"]
    assert "5" in err and "6" in err
    print(f"  ✓ rejected: {err}")
    print("  PASS")


if __name__ == "__main__":
    try:
        test_batch_4_valid()
        test_batch_with_bom()
        test_batch_oversize()
        test_batch_too_many()
        print("\n=== ALL TESTS PASSED ===")
    finally:
        # Always clean up, even if a test fails mid-run, so the
        # user never sees a "我的书库" full of book_1 / clean /
        # with_bom / short again.
        cleanup_test_materials()
        if _TEST_MATERIAL_IDS:
            print(f"\n(cleanup removed {len(_TEST_MATERIAL_IDS)} test materials)")
