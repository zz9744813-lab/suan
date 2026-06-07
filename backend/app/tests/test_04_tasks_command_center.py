"""L1 test_04_tasks_command_center.py — 任务中控台聚合契约。

覆盖昨天 P2 新增的 `/api/tasks/command-center`:
- 固定 6 个 domain
- comment_cleanup / internal 不刷屏
- DeepStudy 顶层任务可见
- active / needs_attention / recent_completed 三个列表聚合正确
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest


async def make_project(db, name="任务中心测试"):
    from app.models.project import Project
    p = Project(name=name, genre="玄幻", target_word_count=100_000, target_chapter_count=100)
    db.add(p)
    await db.flush()
    return p


async def add_task(db, project_id: int, **kw):
    from app.models.task import AgentTask
    row = AgentTask(
        project_id=project_id,
        task_type=kw.pop("task_type", "write_chapter"),
        status=kw.pop("status", "pending"),
        priority=kw.pop("priority", 100),
        payload=kw.pop("payload", {}),
        visibility=kw.pop("visibility", "user"),
        domain=kw.pop("domain", "writing"),
        task_kind=kw.pop("task_kind", None),
        display_title=kw.pop("display_title", None),
        progress_current=kw.pop("progress_current", 0),
        progress_total=kw.pop("progress_total", 0),
        cost_usd=kw.pop("cost_usd", 0.0),
        input_tokens=kw.pop("input_tokens", 0),
        output_tokens=kw.pop("output_tokens", 0),
        started_at=kw.pop("started_at", None),
        finished_at=kw.pop("finished_at", None),
        error=kw.pop("error", None),
        **kw,
    )
    db.add(row)
    await db.flush()
    return row


@pytest.mark.asyncio
class TestCommandCenterEmpty:
    async def test_empty_returns_six_domains(self, client):
        r = await client.get("/api/tasks/command-center")
        assert r.status_code == 200
        data = r.json()["data"]
        domains = data["domains"]
        assert [d["domain"] for d in domains] == [
            "writing", "deepstudy", "discussion", "memory", "model", "export"
        ]
        assert data["active"] == []
        assert data["needs_attention"] == []
        assert data["recent_completed"] == []

    async def test_empty_domain_counts_zero(self, client):
        data = (await client.get("/api/tasks/command-center")).json()["data"]
        for d in data["domains"]:
            assert d["running"] == 0
            assert d["pending"] == 0
            assert d["failed"] == 0
            assert d["succeeded_today"] == 0
            assert d["cost_today"] == 0
            assert d["tokens_today"] == 0


@pytest.mark.asyncio
class TestCommandCenterAggregates:
    async def test_running_writing_task_in_active_and_domain(self, client, db):
        p = await make_project(db)
        task = await add_task(
            db, p.id,
            task_type="write_chapter", domain="writing", status="running",
            display_title="写作: 第 1 章", progress_current=2, progress_total=8,
            cost_usd=0.1234, input_tokens=1000, output_tokens=500,
            started_at=datetime.utcnow(),
        )
        await db.commit()

        data = (await client.get("/api/tasks/command-center")).json()["data"]
        writing = next(d for d in data["domains"] if d["domain"] == "writing")
        assert writing["running"] == 1
        assert writing["current_task_id"] == task.id
        assert writing["current_title"] == "写作: 第 1 章"
        assert writing["progress_current"] == 2
        assert writing["progress_total"] == 8
        assert data["active"][0]["id"] == task.id

    async def test_deepstudy_task_is_visible(self, client, db):
        p = await make_project(db)
        task = await add_task(
            db, p.id,
            task_type="deepstudy_run", domain="deepstudy", status="running",
            display_title="DeepStudy《灵剑山》", progress_current=1, progress_total=853,
            task_kind="deepstudy_run",
        )
        await db.commit()
        data = (await client.get("/api/tasks/command-center")).json()["data"]
        deepstudy = next(d for d in data["domains"] if d["domain"] == "deepstudy")
        assert deepstudy["running"] == 1
        assert deepstudy["current_task_id"] == task.id
        assert data["active"][0]["task_type"] == "deepstudy_run"

    async def test_pending_failed_succeeded_counts(self, client, db):
        p = await make_project(db)
        await add_task(db, p.id, task_type="write_chapter", domain="writing", status="pending")
        await add_task(db, p.id, task_type="write_chapter", domain="writing", status="failed", error="boom")
        await add_task(
            db, p.id, task_type="write_chapter", domain="writing", status="succeeded",
            finished_at=datetime.utcnow(), cost_usd=0.25, input_tokens=200, output_tokens=300,
        )
        await db.commit()
        data = (await client.get("/api/tasks/command-center")).json()["data"]
        writing = next(d for d in data["domains"] if d["domain"] == "writing")
        assert writing["pending"] == 1
        assert writing["failed"] == 1
        assert writing["succeeded_today"] == 1
        assert writing["cost_today"] == 0.25
        assert writing["tokens_today"] == 500


@pytest.mark.asyncio
class TestCommandCenterFiltering:
    async def test_comment_cleanup_is_hidden(self, client, db):
        p = await make_project(db)
        await add_task(
            db, p.id,
            task_type="comment_cleanup", domain="review", status="failed",
            visibility="internal", task_kind="comment_cleanup",
            display_title="评论清理", error="cleanup failed",
        )
        await db.commit()
        data = (await client.get("/api/tasks/command-center")).json()["data"]
        all_items = data["active"] + data["needs_attention"] + data["recent_completed"]
        assert all(t["task_type"] != "comment_cleanup" for t in all_items)
        assert all(d["failed"] == 0 for d in data["domains"])

    async def test_hidden_task_kind_is_hidden_even_if_visibility_user(self, client, db):
        p = await make_project(db)
        await add_task(
            db, p.id,
            task_type="study_stage", domain="deepstudy", status="running",
            visibility="user", task_kind="deepstudy_stage",
            display_title="内部 stage",
        )
        await db.commit()
        data = (await client.get("/api/tasks/command-center")).json()["data"]
        assert data["active"] == []
        deepstudy = next(d for d in data["domains"] if d["domain"] == "deepstudy")
        assert deepstudy["running"] == 0

    async def test_visibility_internal_hidden(self, client, db):
        p = await make_project(db)
        await add_task(
            db, p.id, task_type="provider_health", domain="model", status="running",
            visibility="internal", display_title="provider heartbeat",
        )
        await db.commit()
        data = (await client.get("/api/tasks/command-center")).json()["data"]
        model = next(d for d in data["domains"] if d["domain"] == "model")
        assert model["running"] == 0


@pytest.mark.asyncio
class TestCommandCenterLists:
    async def test_needs_attention_failed_only_current_behavior(self, client, db):
        """当前实现: needs_attention 只收 failed, 不把 running 超时任务算 blocked。

        blocked 超时逻辑是后续增强项, 这里锁当前真实行为。
        """
        p = await make_project(db)
        failed = await add_task(db, p.id, task_type="write_chapter", domain="writing", status="failed", error="bad")
        blocked = await add_task(
            db, p.id, task_type="write_chapter", domain="writing", status="running",
            started_at=datetime.utcnow() - timedelta(minutes=31), display_title="卡住",
        )
        await db.commit()
        data = (await client.get("/api/tasks/command-center")).json()["data"]
        ids = [t["id"] for t in data["needs_attention"]]
        assert failed.id in ids
        assert blocked.id not in ids

    async def test_recent_completed_only_24h(self, client, db):
        p = await make_project(db)
        recent = await add_task(
            db, p.id, task_type="write_chapter", domain="writing", status="succeeded",
            finished_at=datetime.utcnow() - timedelta(hours=1), display_title="最近完成",
        )
        await add_task(
            db, p.id, task_type="write_chapter", domain="writing", status="succeeded",
            finished_at=datetime.utcnow() - timedelta(days=2), display_title="很久以前",
        )
        await db.commit()
        data = (await client.get("/api/tasks/command-center")).json()["data"]
        ids = [t["id"] for t in data["recent_completed"]]
        assert recent.id in ids
        assert len(ids) == 1

    async def test_active_limit_five(self, client, db):
        p = await make_project(db)
        for i in range(7):
            await add_task(db, p.id, task_type="write_chapter", domain="writing", status="running", display_title=f"t{i}")
        await db.commit()
        data = (await client.get("/api/tasks/command-center")).json()["data"]
        assert len(data["active"]) == 5
