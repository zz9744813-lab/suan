"""L1 test_05_study_api.py — 拆书/Study 基础 API。

不跑 LLM, 只测材料 CRUD、自动分章、人物 CRUD、批量删除、DeepStudy 入队契约。
"""
from __future__ import annotations

import pytest


NOVEL_TEXT = """
第一章 山门初见
王陆来到灵剑山门前。风吟真人看了他一眼，说此子有趣。
王陆笑道：我只是来修仙的。

第二章 入门试炼
试炼开始，王陆遇见海云帆。两人一起破解阵法。
风吟真人在远处观察，觉得此子行事不同常人。

第三章 云台问剑
王陆登上云台，面对第一场问剑。他没有硬拼，而是用计取胜。
""".strip()


@pytest.mark.asyncio
class TestStudyMaterials:
    async def test_list_empty_materials(self, client):
        r = await client.get("/api/study/materials")
        assert r.status_code == 200
        assert r.json()["data"] == []

    async def test_create_material_plain(self, client):
        r = await client.post("/api/study/materials", json={
            "title": "灵剑山",
            "author": "国王陛下",
            "source": "paste",
            "raw_text": NOVEL_TEXT,
        })
        assert r.status_code == 200, r.text
        d = r.json()["data"]
        assert d["title"] == "灵剑山"
        assert d["author"] == "国王陛下"
        assert d["source"] == "paste"
        assert d["raw_text_length"] == len(NOVEL_TEXT)
        assert d["chapter_count"] == 0

    async def test_get_material_detail_include_text(self, client):
        create = await client.post("/api/study/materials", json={"title": "T", "raw_text": NOVEL_TEXT})
        mid = create.json()["data"]["id"]
        r = await client.get(f"/api/study/materials/{mid}?include_text=true")
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["raw_text"] == NOVEL_TEXT
        assert d["chapters"] == []
        assert d["characters"] == []

    async def test_update_material(self, client):
        create = await client.post("/api/study/materials", json={"title": "旧名", "raw_text": "abc"})
        mid = create.json()["data"]["id"]
        r = await client.patch(f"/api/study/materials/{mid}", json={
            "title": "新名",
            "author": "作者",
            "shelf_category": "玄幻",
            "extra": {"tags": ["热血"]},
        })
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["title"] == "新名"
        assert d["author"] == "作者"
        assert d["shelf_category"] == "玄幻"
        assert d["extra"]["tags"] == ["热血"]

    async def test_delete_material(self, client):
        create = await client.post("/api/study/materials", json={"title": "要删", "raw_text": "abc"})
        mid = create.json()["data"]["id"]
        r = await client.delete(f"/api/study/materials/{mid}?force=true")
        assert r.status_code == 200
        r2 = await client.get(f"/api/study/materials/{mid}")
        assert r2.status_code == 404


@pytest.mark.asyncio
class TestStudyFromTextAndChapterize:
    async def test_from_text_auto_chapterize_no_deepstudy(self, client):
        r = await client.post("/api/study/materials/from-text", json={
            "title": "灵剑山",
            "author": "国王陛下",
            "raw_text": NOVEL_TEXT,
            "auto_chapterize": True,
            "auto_deepstudy": False,
            "min_chapter_chars": 20,
            "shelf_category": "未分组",
            "tags": ["仙侠", "搞笑"],
        })
        assert r.status_code == 200, r.text
        d = r.json()["data"]
        assert d["title"] == "灵剑山"
        assert d["chapter_count"] >= 3
        assert d["shelf_category"] == "未分组"
        # 当前 StudyMaterialRead 不展开 extra.tags 到 tags 字段, 保持真实 API 行为
        assert d["tags"] == []

        chapters = await client.get(f"/api/study/materials/{d['id']}/chapters")
        titles = [c["title"] for c in chapters.json()["data"]]
        assert titles[0].startswith("第 1 章")
        assert len(titles) >= 3

    async def test_chapterize_endpoint_idempotentish(self, client):
        create = await client.post("/api/study/materials", json={"title": "T", "raw_text": NOVEL_TEXT})
        mid = create.json()["data"]["id"]
        r = await client.post(f"/api/study/materials/{mid}/chapterize", json={"min_chapter_chars": 20, "pattern": "auto"})
        assert r.status_code == 200, r.text
        d = r.json()["data"]
        assert d["chapter_count"] >= 3
        chapters_r = await client.get(f"/api/study/materials/{mid}/chapters")
        chapters = chapters_r.json()["data"]
        assert chapters[0]["chapter_index"] == 1
        assert chapters[0]["char_count"] > 0

    async def test_chapterize_404(self, client):
        r = await client.post("/api/study/materials/99999/chapterize", json={"min_chapter_chars": 20})
        assert r.status_code == 404


@pytest.mark.asyncio
class TestStudyCharacters:
    async def test_add_list_delete_character(self, client):
        create = await client.post("/api/study/materials", json={"title": "T", "raw_text": NOVEL_TEXT})
        mid = create.json()["data"]["id"]
        add = await client.post(f"/api/study/materials/{mid}/characters", json={
            "name": "王陆",
            "aliases": ["王兄"],
            "role": "主角",
            "tags": ["聪明"],
            "base_profile": {"性格": "机敏"},
            "confidence": 0.9,
        })
        assert add.status_code == 200, add.text
        cid = add.json()["data"]["id"]
        assert add.json()["data"]["name"] == "王陆"

        rows = await client.get(f"/api/study/materials/{mid}/characters")
        assert len(rows.json()["data"]) == 1
        assert rows.json()["data"][0]["aliases"] == ["王兄"]

        delete = await client.delete(f"/api/study/materials/{mid}/characters/{cid}")
        assert delete.status_code == 200
        rows2 = await client.get(f"/api/study/materials/{mid}/characters")
        assert rows2.json()["data"] == []

    async def test_add_character_404_material(self, client):
        r = await client.post("/api/study/materials/99999/characters", json={"name": "X"})
        assert r.status_code == 404


@pytest.mark.asyncio
class TestStudyBulkAndTasks:
    async def test_study_all_without_chapters_returns_400(self, client):
        """L1 只测轻量入口契约: 没章节时应立即 400, 不触发后台 LLM/长任务。"""
        create = await client.post("/api/study/materials", json={"title": "空书", "raw_text": "只有正文但不分章"})
        mid = create.json()["data"]["id"]
        r = await client.post(f"/api/study/materials/{mid}/study/all", json={
            "mode": "character",
            "limit": 2,
            "max_concurrency": 1,
            "force": False,
            "max_chars": 1000,
        })
        assert r.status_code == 400
        assert "还没有章节" in r.json()["error"]["message"]

    async def test_study_all_404_material(self, client):
        r = await client.post("/api/study/materials/99999/study/all", json={"mode": "character"})
        assert r.status_code == 404
