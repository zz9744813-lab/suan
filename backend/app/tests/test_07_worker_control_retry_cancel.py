"""L3 test_07_worker_control_retry_cancel.py — Worker 控制 + task retry/cancel。

注意: /api/worker/start 会启动后台 loop, 每个测试最后必须 stop。
测试只验证控制面, 不让 worker 跑真实 LLM。
"""
from __future__ import annotations

import pytest
import pytest_asyncio


@pytest_asyncio.fixture(autouse=True)
async def isolated_worker(monkeypatch):
    import app.routers.worker as worker_router
    import app.workers.worker as worker_module

    async def inert_run_forever(self):
        await self._stop.wait()

    monkeypatch.setattr(worker_module.WorkerController, "_run_forever", inert_run_forever)
    controller = worker_module.WorkerController()
    monkeypatch.setattr(worker_module, "_worker_singleton", controller)
    monkeypatch.setattr(worker_module, "get_worker", lambda: controller)
    monkeypatch.setattr(worker_router, "get_worker", lambda: controller)
    yield
    await controller.stop()


async def make_project_and_task(db, *, status="failed", error="boom"):
    from app.models.project import Project
    from app.models.task import AgentTask
    p = Project(name="Worker 控制测试", genre="玄幻", target_word_count=100_000, target_chapter_count=100)
    db.add(p)
    await db.flush()
    t = AgentTask(
        project_id=p.id,
        task_type="write_chapter",
        status=status,
        error=error,
        retry_count=0,
        domain="writing",
        visibility="user",
        payload={"old": True},
    )
    db.add(t)
    await db.flush()
    await db.commit()
    return p, t


@pytest.mark.asyncio
class TestWorkerControl:
    async def test_status_shape(self, client):
        r = await client.get("/api/worker/status")
        assert r.status_code == 200
        d = r.json()["data"]
        assert "state" in d
        assert "is_loop_alive" in d
        assert "current_task_id" in d

    async def test_start_pause_resume_stop(self, client):
        start = await client.post("/api/worker/start")
        assert start.status_code == 200
        assert start.json()["data"]["started"] is True
        try:
            pause = await client.post("/api/worker/pause")
            assert pause.status_code == 200
            assert pause.json()["data"]["paused"] is True
            assert pause.json()["data"]["status"]["state"] == "paused"

            resume = await client.post("/api/worker/resume")
            assert resume.status_code == 200
            assert resume.json()["data"]["resumed"] is True
            assert resume.json()["data"]["status"]["state"] in {"idle", "running"}
        finally:
            stop = await client.post("/api/worker/stop")
            assert stop.status_code == 200
            assert stop.json()["data"]["stopped"] is True

    async def test_stop_idempotent(self, client):
        r1 = await client.post("/api/worker/stop")
        r2 = await client.post("/api/worker/stop")
        assert r1.status_code == 200
        assert r2.status_code == 200

    async def test_multi_status_returns_workers_list(self, client):
        r = await client.get("/api/worker/multi-status")
        assert r.status_code == 200
        d = r.json()
        assert set(d.keys()) == {
            "writing_worker",
            "deepstudy_worker",
            "discussion_worker",
            "memory_worker",
            "model_router",
        }
        assert "worker_state" in d["writing_worker"]


@pytest.mark.asyncio
class TestTaskCancelRetry:
    async def test_cancel_task(self, client, db):
        _, task = await make_project_and_task(db, status="pending", error=None)
        r = await client.post(f"/api/tasks/{task.id}/cancel")
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["status"] == "cancelled"

    async def test_cancel_task_404(self, client):
        r = await client.post("/api/tasks/99999/cancel")
        assert r.status_code == 404

    async def test_retry_failed_task_default_full(self, client, db):
        _, task = await make_project_and_task(db, status="failed", error="bad")
        r = await client.post(f"/api/tasks/{task.id}/retry", json={})
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["status"] == "pending"
        assert d["retry_count"] == 1
        assert d["error"] is None
        assert d["payload"]["retry_mode"] == "full"

    async def test_retry_with_from_step(self, client, db):
        _, task = await make_project_and_task(db, status="failed", error="bad")
        r = await client.post(f"/api/tasks/{task.id}/retry", json={"mode": "from_failed_step", "from_step": "review"})
        assert r.status_code == 200
        payload = r.json()["data"]["payload"]
        assert payload["retry_mode"] == "from_failed_step"
        assert payload["from_step"] == "review"

    async def test_retry_removes_old_from_step(self, client, db):
        _, task = await make_project_and_task(db, status="failed", error="bad")
        await client.post(f"/api/tasks/{task.id}/retry", json={"mode": "from_failed_step", "from_step": "review"})
        r = await client.post(f"/api/tasks/{task.id}/retry", json={"mode": "full"})
        payload = r.json()["data"]["payload"]
        assert payload["retry_mode"] == "full"
        assert "from_step" not in payload

    async def test_retry_task_404(self, client):
        r = await client.post("/api/tasks/99999/retry", json={})
        assert r.status_code == 404
