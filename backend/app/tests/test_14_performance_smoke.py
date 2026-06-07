"""L11 test_14_performance_smoke.py — 轻量性能/规模 smoke。"""
from __future__ import annotations

import time

import pytest


@pytest.mark.asyncio
class TestPerformanceSmoke:
    async def test_command_center_handles_many_tasks_quickly(self, client, db):
        from app.models.project import Project
        from app.models.task import AgentTask

        project = Project(
            name="性能烟测项目",
            genre="玄幻",
            target_word_count=100_000,
            target_chapter_count=100,
        )
        db.add(project)
        await db.flush()
        db.add_all([
            AgentTask(
                project_id=project.id,
                task_type="write_chapter",
                status="pending" if i % 3 else "running",
                domain="writing",
                visibility="user",
                payload={"idx": i},
            )
            for i in range(1000)
        ])
        await db.commit()

        started = time.perf_counter()
        r = await client.get("/api/tasks/command-center")
        elapsed = time.perf_counter() - started
        assert r.status_code == 200
        data = r.json()["data"]
        assert len(data["active"]) >= 1
        writing = next(item for item in data["domains"] if item["domain"] == "writing")
        assert writing["pending"] > 0
        assert elapsed < 5.0

    async def test_search_handles_many_projects_quickly(self, client, db):
        from app.models.project import Project

        db.add_all([
            Project(
                name=f"规模搜索项目 {i}",
                genre="玄幻",
                description="青云宗 批量性能烟测" if i == 88 else "普通项目",
                target_word_count=100_000,
                target_chapter_count=100,
            )
            for i in range(100)
        ])
        await db.commit()

        started = time.perf_counter()
        r = await client.get("/api/search?q=青云宗")
        elapsed = time.perf_counter() - started
        assert r.status_code == 200
        assert r.json()["total"] >= 1
        assert elapsed < 5.0
