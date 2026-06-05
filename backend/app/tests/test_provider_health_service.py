"""P0 Phase 4: Provider health service tests."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from app.services.provider_health import ProviderHealthService


def _make_provider(**overrides):
    p = MagicMock()
    p.id = 1
    p.name = "test-provider"
    p.base_url = "https://api.example.com"
    p.api_key = "test-key"
    p.enabled = True
    p.default_model = "gpt-4"
    p.model_list = ["gpt-4"]
    p.extra = {}
    p.last_health_full = None
    p.health_score = 0.5
    p.last_health_status = None
    p.last_health_at = None
    p.last_health_latency_ms = None
    for k, v in overrides.items():
        setattr(p, k, v)
    return p


class TestProviderHealthService:
    @pytest.mark.asyncio
    async def test_lightweight_probe_does_not_overwrite_full(self):
        """轻量探针不应覆盖完整探针的 last_health_full."""
        svc = ProviderHealthService(client=AsyncMock())
        # 模拟已有完整探针结果
        existing_full = {
            "results": [{"test": "full_probe", "score": 0.95}],
            "recommended_roles": ["planner", "critic"],
            "score": 0.92,
        }
        provider = _make_provider(last_health_full=dict(existing_full))

        mock_client = AsyncMock()
        mock_client.list_models = AsyncMock(return_value=["gpt-4"])
        svc.client = mock_client

        mock_db = AsyncMock()
        result = await svc.check_provider(mock_db, provider, lightweight=True)

        # last_health_full 应保留 results + recommended_roles
        full = provider.last_health_full
        assert "results" in full
        assert full["results"] == existing_full["results"]
        assert full["recommended_roles"] == existing_full["recommended_roles"]
        # 但 auto_probe 段被更新
        assert "auto_probe" in full
        assert full["auto_probe"]["lightweight"] is True

    @pytest.mark.asyncio
    async def test_full_probe_updates_last_health_full(self):
        """完整探针应更新 last_health_full."""
        svc = ProviderHealthService()
        provider = _make_provider(last_health_full=None)

        mock_client = AsyncMock()
        mock_client.list_models = AsyncMock(return_value=["gpt-4"])
        # mock chat for full probe
        from app.services.llm.client import LLMCallResult
        mock_client.chat = AsyncMock(return_value=LLMCallResult(
            content="hi", model="gpt-4", input_tokens=1, output_tokens=1,
            cost_usd=0.0, duration_ms=100,
            raw={"choices": [{"message": {"content": "hi"}}]},
        ))
        svc.client = mock_client

        mock_db = AsyncMock()
        result = await svc.check_provider(mock_db, provider, lightweight=False)

        assert provider.last_health_full is not None
        assert "auto_probe" in provider.last_health_full
        assert provider.health_score is not None

    @pytest.mark.asyncio
    async def test_all_probes_have_timeout(self):
        """所有探针都应有 timeout (client 构造时设置)."""
        from app.services.llm.client import LLMClient
        client = LLMClient(timeout=120)
        svc = ProviderHealthService(client=client)
        # client 的 timeout 应被正确设置
        assert client.timeout is not None
        assert client.timeout.read > 0

    @pytest.mark.asyncio
    async def test_check_all_enabled(self):
        """check_all_enabled 应检查所有 enabled 的 Provider."""
        svc = ProviderHealthService()
        p1 = _make_provider(id=1, name="p1")
        p2 = _make_provider(id=2, name="p2")

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [p1, p2]
        mock_db.execute = AsyncMock(return_value=mock_result)

        mock_client = AsyncMock()
        mock_client.list_models = AsyncMock(return_value=["gpt-4"])
        svc.client = mock_client

        results = await svc.check_all_enabled(mock_db, lightweight=True)
        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_health_score_range(self):
        """health_score 应在 [0, 1] 范围内."""
        svc = ProviderHealthService()
        provider = _make_provider(last_health_full=None)

        mock_client = AsyncMock()
        mock_client.list_models = AsyncMock(return_value=["gpt-4"])
        svc.client = mock_client

        mock_db = AsyncMock()
        await svc.check_provider(mock_db, provider, lightweight=True)

        assert 0.0 <= provider.health_score <= 1.0
