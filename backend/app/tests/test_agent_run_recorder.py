"""P0 Phase 6: AgentRun recorder tests."""
import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, timedelta

from app.services.agent_run_recorder import AgentRunRecorder


def _make_event(**overrides):
    e = MagicMock()
    e.id = 1
    e.provider_id = 1
    e.model_name = "gpt-4"
    e.agent_role_key = "planner"
    e.project_id = 1
    e.task_id = 1
    e.selection_mode = "auto"
    e.selection_score = 0.8
    e.selection_reason = "test"
    e.status = "success"
    e.failure_type = None
    e.failure_message = None
    e.latency_ms = 500
    e.input_tokens = 100
    e.output_tokens = 200
    e.cost_usd = 0.01
    e.created_at = datetime.utcnow()
    for k, v in overrides.items():
        setattr(e, k, v)
    return e


def _make_provider(**overrides):
    p = MagicMock()
    p.id = 1
    p.name = "test-provider"
    p.enabled = True
    p.circuit_state = "closed"
    p.health_score = 0.9
    p.last_health_status = "healthy"
    p.last_health_at = datetime.utcnow()
    for k, v in overrides.items():
        setattr(p, k, v)
    return p


class TestAgentRunRecorder:
    @pytest.mark.asyncio
    async def test_get_summary_returns_structure(self):
        """get_summary 应返回正确的数据结构."""
        recorder = AgentRunRecorder()
        e1 = _make_event(status="success", agent_role_key="planner", provider_id=1)
        e2 = _make_event(id=2, status="failed", agent_role_key="drafter", failure_type="timeout", provider_id=2)

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [e1, e2]
        mock_db.execute = AsyncMock(return_value=mock_result)

        summary = await recorder.get_summary(mock_db, hours=24)

        assert "total_calls" in summary
        assert "success_calls" in summary
        assert "failed_calls" in summary
        assert "fallback_calls" in summary
        assert "success_rate" in summary
        assert "total_cost_usd" in summary
        assert "by_role" in summary
        assert "by_failure_type" in summary
        assert "by_provider" in summary
        assert summary["total_calls"] == 2
        assert summary["success_calls"] == 1
        assert summary["failed_calls"] == 1

    @pytest.mark.asyncio
    async def test_get_recent_events_sorted_by_id_desc(self):
        """事件应按 id 降序排列."""
        recorder = AgentRunRecorder()
        e1 = _make_event(id=1)
        e2 = _make_event(id=2)
        e3 = _make_event(id=3)

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [e3, e2, e1]
        mock_db.execute = AsyncMock(return_value=mock_result)

        events = await recorder.get_recent_events(mock_db, limit=50)

        # 验证查询使用了 desc ordering
        assert len(events) == 3
        # 结果应按 id 降序 (查询时已 order_by desc)
        assert events[0]["id"] == 3

    @pytest.mark.asyncio
    async def test_get_provider_stats_includes_all_providers(self):
        """统计应包含所有 Provider."""
        recorder = AgentRunRecorder()

        e1 = _make_event(provider_id=1, status="success")
        e2 = _make_event(id=2, provider_id=2, status="success")

        p1 = _make_provider(id=1, name="provider-1")
        p2 = _make_provider(id=2, name="provider-2")

        mock_db = AsyncMock()

        call_count = 0
        def mock_execute(q):
            nonlocal call_count
            call_count += 1
            r = MagicMock()
            if call_count == 1:
                # events query
                r.scalars.return_value.all.return_value = [e1, e2]
            else:
                # providers query
                r.scalars.return_value.all.return_value = [p1, p2]
            return r

        mock_db.execute = AsyncMock(side_effect=mock_execute)

        stats = await recorder.get_provider_stats(mock_db, hours=24)

        assert len(stats) == 2
        provider_ids = [s["provider_id"] for s in stats]
        assert 1 in provider_ids
        assert 2 in provider_ids

    @pytest.mark.asyncio
    async def test_summary_by_role_counts(self):
        """by_role 应正确统计各角色调用."""
        recorder = AgentRunRecorder()
        e1 = _make_event(agent_role_key="planner", status="success")
        e2 = _make_event(id=2, agent_role_key="planner", status="failed", failure_type="timeout")
        e3 = _make_event(id=3, agent_role_key="drafter", status="success")

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [e1, e2, e3]
        mock_db.execute = AsyncMock(return_value=mock_result)

        summary = await recorder.get_summary(mock_db, hours=24)

        assert "planner" in summary["by_role"]
        assert "drafter" in summary["by_role"]
        assert summary["by_role"]["planner"]["total"] == 2
        assert summary["by_role"]["drafter"]["total"] == 1

    @pytest.mark.asyncio
    async def test_summary_empty_events(self):
        """无事件时应返回零值统计."""
        recorder = AgentRunRecorder()

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)

        summary = await recorder.get_summary(mock_db, hours=24)

        assert summary["total_calls"] == 0
        assert summary["success_rate"] == 0.0
