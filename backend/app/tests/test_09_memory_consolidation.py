"""L5 test_09_memory_consolidation.py — 项目记忆二次加工轻量契约。"""
from __future__ import annotations

import pytest


async def make_memory_project(db):
    from app.models.project import Project

    project = Project(
        name="记忆整合测试",
        genre="玄幻",
        target_word_count=100_000,
        target_chapter_count=100,
    )
    db.add(project)
    await db.flush()
    await db.commit()
    return project


@pytest.mark.asyncio
class TestMemoryConsolidation:
    async def test_consolidate_marks_raw_entries_processed(self, client, db):
        from app.models.memory_v2 import RawMemoryEntry

        project = await make_memory_project(db)
        raw = RawMemoryEntry(
            project_id=project.id,
            chapter_index=1,
            entry_type="character_state",
            subject="苏瑶",
            predicate="location",
            object_value="青云宗",
            raw_payload={"location": "青云宗"},
            source_quote="苏瑶回到了青云宗。",
            source_summary="苏瑶位置变化",
            confidence=0.8,
        )
        db.add(raw)
        await db.flush()
        raw_id = raw.id
        await db.commit()

        r = await client.post(f"/api/project-memory/{project.id}/consolidate", json={"batch_limit": 10})
        assert r.status_code == 200
        data = r.json()
        assert data["processed"] == 1
        assert data["merged"] == 0
        assert data["needs_discussion"] == 0

        refreshed = await db.get(RawMemoryEntry, raw_id)
        await db.refresh(refreshed)
        assert refreshed.status == "processed"
        assert refreshed.processed_at is not None

    async def test_archive_overview_and_entities(self, client, db):
        from app.models.memory_v2 import StableMemoryEntity

        project = await make_memory_project(db)
        db.add(StableMemoryEntity(
            project_id=project.id,
            entity_type="character",
            canonical_name="苏瑶",
            aliases=["瑶儿"],
            tags=["女主"],
            profile={"faction": "青云宗"},
            importance=0.9,
            confidence=0.95,
            first_chapter_index=1,
            last_chapter_index=10,
        ))
        await db.commit()

        overview = await client.get(f"/api/project-memory/{project.id}")
        assert overview.status_code == 200
        assert overview.json()["counts"]["character"] == 1
        assert overview.json()["decision_summary"] == {
            "pending": 0,
            "running": 0,
            "decided": 0,
            "failed": 0,
        }

        entities = await client.get(f"/api/project-memory/{project.id}/entities?type=character")
        assert entities.status_code == 200
        data = entities.json()
        assert len(data) == 1
        assert data[0]["canonical_name"] == "苏瑶"

    async def test_empty_project_memory_contracts(self, client, db):
        project = await make_memory_project(db)
        shelf = await client.get("/api/project-memory")
        assert shelf.status_code == 200
        assert len(shelf.json()["system_books"]) == 3
        assert any(item["project_id"] == project.id for item in shelf.json()["items"])

        entities = await client.get(f"/api/project-memory/{project.id}/entities")
        assert entities.status_code == 200
        assert entities.json() == []

    async def test_project_memory_404(self, client):
        r = await client.get("/api/project-memory/99999")
        assert r.status_code == 404
