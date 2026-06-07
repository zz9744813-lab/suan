"""L10 test_13_export_search.py — 导出与全局搜索契约。"""
from __future__ import annotations

import pytest


async def make_export_project(db):
    from app.models.project import Chapter, ChapterVersion, Project

    project = Project(
        name="导出搜索测试",
        genre="玄幻",
        description="包含青云宗关键词",
        target_word_count=100_000,
        target_chapter_count=100,
    )
    db.add(project)
    await db.flush()
    chapter = Chapter(
        project_id=project.id,
        chapter_no=1,
        title="青云宗初遇",
        target_word_count=3000,
        actual_word_count=12,
        status="done",
    )
    db.add(chapter)
    await db.flush()
    db.add(ChapterVersion(
        chapter_id=chapter.id,
        version_kind="final",
        version_no=1,
        content="苏瑶在青云宗遇见林墨。",
        summary="初遇",
        score=88,
    ))
    await db.commit()
    return project, chapter


@pytest.mark.asyncio
class TestExportSearch:
    async def test_project_export_json_and_markdown(self, client, db):
        project, _ = await make_export_project(db)

        json_resp = await client.get(f"/api/projects/{project.id}/export?format=json")
        assert json_resp.status_code == 200
        assert "application/json" in json_resp.headers["content-type"]
        payload = json_resp.json()
        assert payload["project"]["name"] == "导出搜索测试"
        assert payload["chapters"][0]["content"] == "苏瑶在青云宗遇见林墨。"

        md_resp = await client.get(f"/api/projects/{project.id}/export?format=markdown")
        assert md_resp.status_code == 200
        assert "text/markdown" in md_resp.headers["content-type"]
        assert "# 导出搜索测试" in md_resp.text
        assert "苏瑶在青云宗遇见林墨。" in md_resp.text
        assert "Content-Disposition" in md_resp.headers

    async def test_global_search_project_and_chapter(self, client, db):
        project, chapter = await make_export_project(db)
        r = await client.get("/api/search?q=青云宗")
        assert r.status_code == 200
        data = r.json()["data"]
        assert r.json()["total"] >= 2
        assert any(item["type"] == "project" and item["id"] == project.id for item in data)
        assert any(item["type"] == "chapter" and item["id"] == chapter.id for item in data)

    async def test_search_blank_query_contract(self, client):
        r = await client.get("/api/search?q=%20%20")
        assert r.status_code == 200
        assert r.json()["data"] == []
        assert r.json()["total"] == 0

    async def test_export_project_404(self, client):
        r = await client.get("/api/projects/99999/export?format=json")
        assert r.status_code == 404
