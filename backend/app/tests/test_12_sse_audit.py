"""L8 test_12_sse_audit.py — SSE 事件流 + 审计日志契约。"""
from __future__ import annotations

from datetime import datetime

import pytest


@pytest.mark.asyncio
class TestSSEAudit:
    async def test_sse_stream_initial_event_shape(self, monkeypatch):
        from app.core.events import Event
        from app.routers import events as events_router

        async def fake_stream():
            yield Event(event_type="unit.test", payload={"message": "ok"})

        monkeypatch.setattr(events_router, "sse_stream", fake_stream)
        response = await events_router.stream()
        generator = response.body_iterator
        first = await generator.__anext__()
        assert first["event"] == "unit.test"
        assert "message" in first["data"]

    async def test_audit_logs_filters_and_stats(self, client, db):
        from app.models.audit_log import AuditLog
        from app.models.project import Project

        project = Project(
            name="审计测试",
            genre="玄幻",
            target_word_count=100_000,
            target_chapter_count=100,
        )
        db.add(project)
        await db.flush()
        db.add(AuditLog(
            project_id=project.id,
            event_type="model_switch",
            actor_type="system",
            actor_key="router",
            action="切换模型",
            details={"api_key": "***", "provider": "mock"},
            created_at=datetime.utcnow(),
        ))
        await db.commit()

        logs = await client.get(f"/api/audit/logs?project_id={project.id}&event_type=model_switch")
        assert logs.status_code == 200
        data = logs.json()["data"]
        assert data["total"] == 1
        item = data["items"][0]
        assert item["action"] == "切换模型"
        assert item["details"]["api_key"] == "***"

        recent = await client.get(f"/api/audit/logs/recent?project_id={project.id}")
        assert recent.status_code == 200
        assert recent.json()["data"][0]["event_type"] == "model_switch"

        stats = await client.get(f"/api/audit/stats/by-event?project_id={project.id}&days=7")
        assert stats.status_code == 200
        assert stats.json()["data"]["counts"]["model_switch"] == 1
