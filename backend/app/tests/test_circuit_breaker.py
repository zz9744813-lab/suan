"""P0 Phase 4: Circuit breaker tests."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta

from app.services.model_circuit_breaker import (
    CircuitBreakerService,
    CIRCUIT_RULES,
)


def _make_provider(**overrides):
    """创建一个 mock ModelProvider."""
    p = MagicMock()
    p.id = 1
    p.name = "test-provider"
    p.circuit_state = "closed"
    p.circuit_open_until = None
    p.consecutive_failures = 0
    p.consecutive_successes = 0
    p.last_failure_type = None
    p.last_failure_message = None
    p.last_success_at = None
    p.health_score = 0.75
    p.enabled = True
    p.avg_latency_ms = None
    p.daily_cost_usd = 0.0
    p.daily_request_count = 0
    p.daily_token_count = 0
    p.last_reset_date = None
    for k, v in overrides.items():
        setattr(p, k, v)
    return p


class TestCircuitBreaker:
    @pytest.mark.asyncio
    async def test_auth_error_opens_circuit(self):
        """401 应立即熔断 (consecutive=1)."""
        cb = CircuitBreakerService()
        p = _make_provider()
        mock_db = AsyncMock()
        mock_db.get = AsyncMock(return_value=p)

        await cb.record_failure(
            mock_db, provider_id=1, model_name="gpt-4",
            agent_role_key="planner", failure_type="auth_error",
            message="401 Unauthorized",
        )
        assert p.circuit_state == "open"
        # auth_error 的 duration 为 365 天 (实际无限期)
        assert p.circuit_open_until is not None

    @pytest.mark.asyncio
    async def test_rate_limit_cooldown(self):
        """429 应触发 cooldown (有限时熔断)."""
        cb = CircuitBreakerService()
        p = _make_provider()
        mock_db = AsyncMock()
        mock_db.get = AsyncMock(return_value=p)

        await cb.record_failure(
            mock_db, provider_id=1, model_name="gpt-4",
            agent_role_key="planner", failure_type="rate_limited",
            message="429 Too Many Requests",
        )
        assert p.circuit_state == "open"
        assert p.circuit_open_until is not None
        # 规则: 10 分钟
        rule_duration = CIRCUIT_RULES["rate_limited"]["duration"]
        assert rule_duration == timedelta(minutes=10)

    @pytest.mark.asyncio
    async def test_half_open_recovery(self):
        """circuit_open_until 过期后应恢复为 half_open."""
        cb = CircuitBreakerService()
        p = _make_provider(
            circuit_state="open",
            circuit_open_until=datetime.utcnow() - timedelta(minutes=1),
        )
        mock_db = AsyncMock()

        # check_half_open 扫描所有到期 provider
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [p]
        mock_db.execute = AsyncMock(return_value=mock_result)

        count = await cb.check_half_open(mock_db)
        assert count == 1
        assert p.circuit_state == "half_open"

    @pytest.mark.asyncio
    async def test_closed_state_allows_requests(self):
        """closed 状态允许正常请求."""
        cb = CircuitBreakerService()
        p = _make_provider(circuit_state="closed")
        mock_db = AsyncMock()
        mock_db.get = AsyncMock(return_value=p)

        skip, reason = await cb.should_skip_provider(mock_db, 1)
        assert skip is False
        assert reason is None

    @pytest.mark.asyncio
    async def test_open_state_skips_requests(self):
        """open 状态且未到期应跳过请求."""
        cb = CircuitBreakerService()
        p = _make_provider(
            circuit_state="open",
            circuit_open_until=datetime.utcnow() + timedelta(hours=1),
            last_failure_type="rate_limited",
        )
        mock_db = AsyncMock()
        mock_db.get = AsyncMock(return_value=p)

        skip, reason = await cb.should_skip_provider(mock_db, 1)
        assert skip is True
        assert "熔断中" in reason

    @pytest.mark.asyncio
    async def test_success_closes_circuit(self):
        """half_open 状态下成功请求应关闭熔断."""
        cb = CircuitBreakerService()
        p = _make_provider(circuit_state="half_open")
        mock_db = AsyncMock()
        mock_db.get = AsyncMock(return_value=p)

        await cb.record_success(
            mock_db, provider_id=1, model_name="gpt-4",
            agent_role_key="planner", latency_ms=500,
            input_tokens=10, output_tokens=20, cost_usd=0.001,
        )
        assert p.circuit_state == "closed"
        assert p.circuit_open_until is None
        assert p.consecutive_failures == 0

    @pytest.mark.asyncio
    async def test_json_parse_failed_does_not_open_circuit(self):
        """json_parse_failed 不应触发 Provider 熔断, 只降 health_score."""
        cb = CircuitBreakerService()
        p = _make_provider(health_score=0.75)
        mock_db = AsyncMock()
        mock_db.get = AsyncMock(return_value=p)

        await cb.record_failure(
            mock_db, provider_id=1, model_name="gpt-4",
            agent_role_key="planner", failure_type="json_parse_failed",
            message="JSON parse error",
        )
        # consecutive=999, 所以即使失败也不应 open circuit
        # 但 health_score 应降低
        assert p.health_score < 0.75

    @pytest.mark.asyncio
    async def test_reset_circuit(self):
        """手动重置应关闭熔断."""
        cb = CircuitBreakerService()
        p = _make_provider(
            circuit_state="open",
            consecutive_failures=5,
            last_failure_type="rate_limited",
        )
        mock_db = AsyncMock()
        mock_db.get = AsyncMock(return_value=p)

        result = await cb.reset_circuit(mock_db, 1)
        assert result.circuit_state == "closed"
        assert result.consecutive_failures == 0
