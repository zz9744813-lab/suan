"""L6 test_10_deepstudy_graph.py — DeepStudy run scaffold + 知识图谱契约。"""
from __future__ import annotations

import pytest


async def make_material_with_chapters(db):
    from app.models.project import Project
    from app.models.study import StudyChapter, StudyMaterial

    project = Project(
        name="DeepStudy 图谱测试",
        genre="玄幻",
        target_word_count=100_000,
        target_chapter_count=100,
    )
    db.add(project)
    await db.flush()
    material = StudyMaterial(
        project_id=project.id,
        title="样书",
        author="测试作者",
        raw_text="第一章\n苏瑶出现。\n第二章\n林墨登场。",
        status="ready",
        study_status="chapterized",
        chapter_count=2,
        shelf_category="玄幻",
    )
    db.add(material)
    await db.flush()
    db.add_all([
        StudyChapter(material_id=material.id, chapter_index=1, title="第一章", content="苏瑶出现", char_count=4),
        StudyChapter(material_id=material.id, chapter_index=2, title="第二章", content="林墨登场", char_count=4),
    ])
    await db.flush()
    await db.commit()
    return project, material


@pytest.mark.asyncio
class TestDeepStudyGraph:
    async def test_run_lifecycle_scaffold(self, client, db):
        _, material = await make_material_with_chapters(db)
        start = await client.post(f"/api/deepstudy/materials/{material.id}/runs", json={
            "mode": "entities_only",
            "chapter_range": [1, 2],
            "max_concurrency": 2,
        })
        assert start.status_code == 200
        data = start.json()["data"]
        assert data["status"] == "queued"

        run = await client.get(f"/api/deepstudy/runs/{data['run_id']}")
        assert run.status_code == 200
        run_data = run.json()["data"]
        assert run_data["total_chapters"] == 2
        assert run_data["agent_plan"]["mode"] == "entities_only"
        assert "entity_extract" in run_data["agent_plan"]["stages"]

        paused = await client.post(f"/api/deepstudy/runs/{data['run_id']}/pause")
        assert paused.status_code == 200
        assert paused.json()["data"]["status"] == "paused"

        resumed = await client.post(f"/api/deepstudy/runs/{data['run_id']}/resume")
        assert resumed.status_code == 200
        assert resumed.json()["data"]["status"] == "running"

        cancelled = await client.post(f"/api/deepstudy/runs/{data['run_id']}/cancel")
        assert cancelled.status_code == 200
        assert cancelled.json()["data"]["status"] == "cancelled"

        pause_terminal = await client.post(f"/api/deepstudy/runs/{data['run_id']}/pause")
        assert pause_terminal.status_code == 400

    async def test_knowledge_graph_filters_and_focus(self, client, db):
        from app.models.deepstudy import Entity, Relationship

        _, material = await make_material_with_chapters(db)
        suyao = Entity(
            material_id=material.id,
            entity_type="character",
            name="苏瑶",
            aliases=["瑶儿"],
            tags=["女主"],
            importance=0.9,
            confidence=0.95,
            first_chapter_index=1,
        )
        linmo = Entity(
            material_id=material.id,
            entity_type="character",
            name="林墨",
            tags=["男主"],
            importance=0.8,
            confidence=0.9,
            first_chapter_index=2,
        )
        low = Entity(
            material_id=material.id,
            entity_type="object",
            name="低置信物品",
            confidence=0.2,
        )
        db.add_all([suyao, linmo, low])
        await db.flush()
        db.add(Relationship(
            material_id=material.id,
            source_entity_id=suyao.id,
            target_entity_id=linmo.id,
            relation_type="ally",
            relation_label="同盟",
            strength=0.7,
            confidence=0.9,
            change_summary="共同对抗外敌",
            evidence_quotes=["二人并肩"],
        ))
        await db.commit()

        graph = await client.get(f"/api/deepstudy/materials/{material.id}/knowledge-graph?min_confidence=0.8")
        assert graph.status_code == 200
        data = graph.json()["data"]
        labels = {n["label"] for n in data["nodes"]}
        assert {"样书", "苏瑶", "林墨"}.issubset(labels)
        assert "低置信物品" not in labels
        assert data["stats"]["by_type"]["book"] == 1
        assert data["stats"]["by_type"]["character"] == 2
        assert len(data["edges"]) == 1

        focus = await client.get(f"/api/deepstudy/materials/{material.id}/knowledge-graph?focus_node_id=entity:{suyao.id}&min_confidence=0.8")
        assert focus.status_code == 200
        focus_ids = {n["id"] for n in focus.json()["data"]["nodes"]}
        assert {f"book:{material.id}", f"entity:{suyao.id}", f"entity:{linmo.id}"}.issubset(focus_ids)

    async def test_deepstudy_not_found_contracts(self, client):
        r = await client.post("/api/deepstudy/materials/99999/runs", json={})
        assert r.status_code == 404
        graph = await client.get("/api/deepstudy/materials/99999/knowledge-graph")
        assert graph.status_code == 404
