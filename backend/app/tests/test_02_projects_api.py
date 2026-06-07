"""L1 test_02_projects_api.py — 真 DB 集成测试。

策略: conftest session 起手时已 TRUNCATE 业务表, 这里造新数据测。
"""
from __future__ import annotations

import pytest


@pytest.mark.asyncio
class TestProjectsList:
    """GET /api/projects 列表端点 — P0 修过的 include_system 过滤必须有效"""

    async def test_empty_after_truncate(self, client):
        """TRUNCATE 后, 默认列表返空 (系统项目被默认隐藏)"""
        r = await client.get("/api/projects")
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is True
        assert body["data"] == []

    async def test_include_system_also_empty_after_truncate(self, client):
        """TRUNCATE 后, include_system=true 也返空 (没系统项目)"""
        r = await client.get("/api/projects?include_system=true")
        assert r.status_code == 200
        assert r.json()["data"] == []


@pytest.mark.asyncio
class TestProjectsCreate:
    """POST /api/projects — P0 修过的 name 必填保护"""

    async def test_create_with_name(self, client):
        r = await client.post("/api/projects", json={
            "name": "测试书",
            "genre": "玄幻",
            "target_word_count": 3_000_000,
            "target_chapter_count": 2000,
        })
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is True
        p = body["data"]
        assert p["name"] == "测试书"
        assert p["genre"] == "玄幻"
        assert p["target_word_count"] == 3_000_000
        assert p["id"] > 0

    async def test_create_with_pinned(self, client):
        r = await client.post("/api/projects", json={
            "name": "置顶测试", "genre": "科幻", "pinned": True,
            "target_word_count": 1_000_000, "target_chapter_count": 500,
        })
        assert r.status_code == 200
        assert r.json()["data"]["pinned"] is True

    async def test_create_with_description(self, client):
        r = await client.post("/api/projects", json={
            "name": "带简介",
            "genre": "悬疑",
            "description": "一部推理小说",
            "target_word_count": 500_000,
            "target_chapter_count": 200,
        })
        assert r.status_code == 200
        assert r.json()["data"]["description"] == "一部推理小说"

    async def test_create_rejects_empty_name(self, client):
        """P0 修过的 name 必填保护"""
        r = await client.post("/api/projects", json={
            "name": "   ",  # 全空白
            "genre": "玄幻",
        })
        # 应该 400 (后端 trim 后判空)
        assert r.status_code == 400
        body = r.json()
        assert body["ok"] is False
        assert body["error"]["type"] == "BadRequest"
        assert "名称不能为空" in body["error"]["message"]

    async def test_create_rejects_too_long_name(self, client):
        r = await client.post("/api/projects", json={
            "name": "x" * 201,  # 201 字
            "genre": "玄幻",
        })
        # schema 层 max_length=200 先拦截, FastAPI 返回 422
        assert r.status_code == 422


@pytest.mark.asyncio
class TestProjectsListAfterCreate:
    """P0 include_system 过滤的最终验收"""

    async def test_list_excludes_system_after_create_normal(self, client):
        """创建 1 个普通项目, 默认列表应该看到 1 个"""
        await client.post("/api/projects", json={
            "name": "A 项目", "genre": "玄幻",
            "target_word_count": 1_000_000, "target_chapter_count": 100,
        })
        r = await client.get("/api/projects")
        body = r.json()["data"]
        assert len(body) == 1
        assert body[0]["name"] == "A 项目"

    async def test_list_excludes_study_category(self, client, db):
        """category=study 的项目默认隐藏 (P0 修过)。直接 ORM 插入, 因为 POST schema 不允许系统 category。"""
        from app.models.project import Project
        db.add(Project(name="应被隐藏", genre="玄幻", category="study", target_word_count=1, target_chapter_count=1))
        await db.commit()
        r = await client.get("/api/projects")
        names = [p["name"] for p in r.json()["data"]]
        assert "应被隐藏" not in names

    async def test_list_excludes_genre_system(self, client, db):
        """genre=system 的项目默认隐藏 (P0 修过)。直接 ORM 插入, 因为 POST schema 不允许 system genre。"""
        from app.models.project import Project
        db.add(Project(name="系统测试项目", genre="system", category=None, target_word_count=1, target_chapter_count=1))
        await db.commit()
        r = await client.get("/api/projects")
        names = [p["name"] for p in r.json()["data"]]
        assert "系统测试项目" not in names

    async def test_include_system_includes_hidden(self, client, db):
        """include_system=true 看到所有, 包括 category=study/genre=system"""
        from app.models.project import Project
        db.add(Project(name="系统测试项目", genre="system", category=None, target_word_count=1, target_chapter_count=1))
        await db.commit()
        r = await client.get("/api/projects?include_system=true")
        names = [p["name"] for p in r.json()["data"]]
        assert "系统测试项目" in names


@pytest.mark.asyncio
class TestProjectsUpdate:
    """PATCH /api/projects/{id}"""

    async def test_update_name(self, client):
        create = await client.post("/api/projects", json={
            "name": "原名", "genre": "玄幻",
            "target_word_count": 10_000, "target_chapter_count": 10,
        })
        pid = create.json()["data"]["id"]
        r = await client.patch(f"/api/projects/{pid}", json={"name": "新名"})
        assert r.status_code == 200
        assert r.json()["data"]["name"] == "新名"

    async def test_toggle_pinned(self, client):
        create = await client.post("/api/projects", json={
            "name": "P", "genre": "玄幻",
            "target_word_count": 10_000, "target_chapter_count": 10,
        })
        pid = create.json()["data"]["id"]
        r = await client.patch(f"/api/projects/{pid}", json={"pinned": True})
        assert r.json()["data"]["pinned"] is True

    async def test_update_nonexistent_returns_404(self, client):
        r = await client.patch("/api/projects/99999", json={"name": "x"})
        assert r.status_code == 404
        assert r.json()["error"]["type"] == "NotFound"


@pytest.mark.asyncio
class TestProjectsDelete:
    """DELETE /api/projects/{id}"""

    async def test_delete_then_404(self, client):
        create = await client.post("/api/projects", json={
            "name": "要删", "genre": "玄幻",
            "target_word_count": 10_000, "target_chapter_count": 10,
        })
        pid = create.json()["data"]["id"]
        r = await client.delete(f"/api/projects/{pid}")
        assert r.status_code == 200
        # 再 get 应该 404
        r2 = await client.get(f"/api/projects/{pid}")
        assert r2.status_code == 404

    async def test_delete_nonexistent_404(self, client):
        r = await client.delete("/api/projects/99999")
        assert r.status_code == 404
