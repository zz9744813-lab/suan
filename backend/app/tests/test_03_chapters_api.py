"""L1 test_03_chapters_api.py — 项目子资源: Bible / Outlines / Chapters / Versions / Steps。

这些测试走真 DB + HTTP API, 由 conftest 在每个 test 前 TRUNCATE。
"""
from __future__ import annotations

import pytest


async def make_project(client, name="章节测试书") -> int:
    r = await client.post("/api/projects", json={
        "name": name,
        "genre": "玄幻",
        "target_word_count": 100_000,
        "target_chapter_count": 100,
    })
    assert r.status_code == 200, r.text
    return r.json()["data"]["id"]


@pytest.mark.asyncio
class TestBibleAPI:
    async def test_get_bible_auto_created(self, client):
        """新项目读取 bible 会自动返回默认设定集。"""
        pid = await make_project(client)
        r = await client.get(f"/api/projects/{pid}/bible")
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["project_id"] == pid
        assert d["is_active"] is True

    async def test_put_then_get_bible(self, client):
        pid = await make_project(client)
        payload = {"title": "设定集", "content": {"world": "灵气复苏", "tone": "热血"}}
        r = await client.put(f"/api/projects/{pid}/bible", json=payload)
        assert r.status_code == 200, r.text
        d = r.json()["data"]
        assert d["project_id"] == pid
        assert d["title"] == "设定集"
        assert d["content"]["world"] == "灵气复苏"
        assert d["is_active"] is True

        r2 = await client.get(f"/api/projects/{pid}/bible")
        assert r2.status_code == 200
        assert r2.json()["data"]["content"]["tone"] == "热血"

    async def test_put_bible_updates_existing_version(self, client):
        pid = await make_project(client)
        await client.put(f"/api/projects/{pid}/bible", json={"title": "v1", "content": {"a": 1}})
        r = await client.put(f"/api/projects/{pid}/bible", json={"title": "v2", "content": {"b": 2}})
        d = r.json()["data"]
        assert d["title"] == "v2"
        assert d["content"] == {"b": 2}


@pytest.mark.asyncio
class TestOutlinesAPI:
    async def test_list_empty_outlines(self, client):
        pid = await make_project(client)
        r = await client.get(f"/api/projects/{pid}/outlines")
        assert r.status_code == 200
        assert r.json()["data"] == []

    async def test_create_outline(self, client):
        pid = await make_project(client)
        r = await client.post(f"/api/projects/{pid}/outlines", json={
            "volume_no": 1,
            "chapter_no": 1,
            "title": "第一章 山门",
            "summary": "主角入山门",
            "importance": 70,
            "is_volume_opener": True,
            "target_word_count": 3200,
        })
        assert r.status_code == 200, r.text
        d = r.json()["data"]
        assert d["project_id"] == pid
        assert d["chapter_no"] == 1
        assert d["title"] == "第一章 山门"
        assert d["status"] == "pending"

    async def test_bulk_create_outlines_ordered(self, client):
        pid = await make_project(client)
        r = await client.post(f"/api/projects/{pid}/outlines/bulk", json=[
            {"volume_no": 1, "chapter_no": 2, "title": "第二章"},
            {"volume_no": 1, "chapter_no": 1, "title": "第一章"},
        ])
        assert r.status_code == 200, r.text
        assert len(r.json()["data"]) == 2
        list_r = await client.get(f"/api/projects/{pid}/outlines")
        nums = [x["chapter_no"] for x in list_r.json()["data"]]
        assert nums == [1, 2]


@pytest.mark.asyncio
class TestChaptersAPI:
    async def test_list_empty_chapters(self, client):
        pid = await make_project(client)
        r = await client.get(f"/api/projects/{pid}/chapters")
        assert r.status_code == 200
        assert r.json()["data"] == []

    async def test_create_chapter(self, client):
        pid = await make_project(client)
        r = await client.post(f"/api/projects/{pid}/chapters", json={
            "chapter_no": 1,
            "title": "第一章",
            "target_word_count": 3000,
        })
        assert r.status_code == 200, r.text
        d = r.json()["data"]
        assert d["project_id"] == pid
        assert d["chapter_no"] == 1
        assert d["status"] == "queued"
        assert d["actual_word_count"] == 0

    async def test_create_chapter_with_outline(self, client):
        pid = await make_project(client)
        outline = await client.post(f"/api/projects/{pid}/outlines", json={"chapter_no": 1, "title": "大纲"})
        oid = outline.json()["data"]["id"]
        ch = await client.post(f"/api/projects/{pid}/chapters", json={
            "outline_id": oid,
            "chapter_no": 1,
            "title": "章节",
        })
        assert ch.status_code == 200
        assert ch.json()["data"]["outline_id"] == oid

    async def test_list_chapters_ordered(self, client):
        pid = await make_project(client)
        await client.post(f"/api/projects/{pid}/chapters", json={"chapter_no": 2, "title": "第二章"})
        await client.post(f"/api/projects/{pid}/chapters", json={"chapter_no": 1, "title": "第一章"})
        r = await client.get(f"/api/projects/{pid}/chapters")
        nums = [x["chapter_no"] for x in r.json()["data"]]
        assert nums == [1, 2]

    async def test_get_chapter_by_id(self, client):
        pid = await make_project(client)
        ch = await client.post(f"/api/projects/{pid}/chapters", json={"chapter_no": 1, "title": "第一章"})
        cid = ch.json()["data"]["id"]
        r = await client.get(f"/api/chapters/{cid}")
        assert r.status_code == 200
        assert r.json()["data"]["id"] == cid

    async def test_get_chapter_404(self, client):
        r = await client.get("/api/chapters/99999")
        assert r.status_code == 404


@pytest.mark.asyncio
class TestChapterVersionsAndSteps:
    async def test_versions_empty(self, client):
        pid = await make_project(client)
        ch = await client.post(f"/api/projects/{pid}/chapters", json={"chapter_no": 1, "title": "第一章"})
        cid = ch.json()["data"]["id"]
        r = await client.get(f"/api/chapters/{cid}/versions")
        assert r.status_code == 200
        assert r.json()["data"] == []

    async def test_latest_version_404(self, client):
        pid = await make_project(client)
        ch = await client.post(f"/api/projects/{pid}/chapters", json={"chapter_no": 1, "title": "第一章"})
        cid = ch.json()["data"]["id"]
        r = await client.get(f"/api/chapters/{cid}/versions/final")
        assert r.status_code == 404
        assert r.json()["error"]["type"] == "NotFound"

    async def test_steps_empty(self, client):
        pid = await make_project(client)
        ch = await client.post(f"/api/projects/{pid}/chapters", json={"chapter_no": 1, "title": "第一章"})
        cid = ch.json()["data"]["id"]
        r = await client.get(f"/api/chapters/{cid}/steps")
        assert r.status_code == 200
        assert r.json()["data"] == []
