"""R19 batch upload API tests.

These tests use the in-process ASGI client from ``conftest`` so they do
not require a dev server on port 8000 and cannot write into the live
``backend/data/novelforge.db``.
"""
from __future__ import annotations

import pytest


def _file(filename: str, content: bytes, content_type: str = "text/plain"):
    return ("files", (filename, content, content_type))


def make_chapter_body(idx: int) -> bytes:
    return f"第 {idx} 章 第 {idx} 章标题\n".encode("utf-8") + ("字" * 250).encode("utf-8")


def make_short_body() -> bytes:
    return "第 1 章 太短\n只有几个字".encode("utf-8")


@pytest.mark.asyncio
async def test_batch_4_valid(client):
    files = [
        _file(f"book_{i}.txt", make_chapter_body(i))
        for i in range(1, 5)
    ]
    response = await client.post(
        "/api/study/materials/upload/batch",
        data={"auto_deepstudy": "false", "auto_start_worker": "false"},
        files=files,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert len(body["data"]) == 4
    for item in body["data"]:
        assert item["ok"] is True, f"expected success: {item}"
        assert item["data"]["chapter_count"] == 1
        assert item["data"]["status"] == "ready"


@pytest.mark.asyncio
async def test_batch_with_bom(client):
    files = [
        _file("clean.txt", make_chapter_body(1)),
        _file("with_bom.txt", b"\xef\xbb\xbf" + make_chapter_body(2)),
        _file("short.txt", make_short_body()),
    ]
    response = await client.post(
        "/api/study/materials/upload/batch",
        data={"auto_deepstudy": "false", "auto_start_worker": "false"},
        files=files,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert len(body["data"]) == 3
    assert all(item["ok"] for item in body["data"])

    bom_result = next(item for item in body["data"] if item["data"]["title"] == "with_bom")
    assert bom_result["data"]["chapter_count"] == 1

    short_result = next(item for item in body["data"] if item["data"]["title"] == "short")
    assert short_result["data"]["chapter_count"] == 0
    assert short_result["data"]["status"] == "draft"


@pytest.mark.asyncio
async def test_batch_oversize(client):
    big = b"x" * (33 * 1024 * 1024)
    response = await client.post(
        "/api/study/materials/upload/batch",
        data={"auto_deepstudy": "false", "auto_start_worker": "false"},
        files=[_file("huge.txt", big)],
    )
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    item = body["data"][0]
    assert item["ok"] is False
    assert "过大" in item["error"]


@pytest.mark.asyncio
async def test_batch_too_many(client):
    files = [
        _file(f"book_{i}.txt", make_chapter_body(i))
        for i in range(1, 7)
    ]
    response = await client.post(
        "/api/study/materials/upload/batch",
        data={"auto_deepstudy": "false", "auto_start_worker": "false"},
        files=files,
    )
    assert response.status_code == 400
    body = response.json()
    assert body["ok"] is False
    message = body["error"]["message"]
    assert "5" in message and "6" in message
