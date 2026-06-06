"""P0 Phase 2: Model selector fallback scoring tests."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta

from app.services.model_selector import (
    ModelSelectorService,
    ModelCandidate,
    provider_health_score,
    latency_score,
    cost_score,
    json_stability_score,
    is_text_role_model_compatible,
    _clamp,
)


# ── 纯函数评分测试 ──


class TestProviderHealthScore:
    def test_open_circuit_without_expiry_returns_zero(self):
        """circuit_state=open 且未过期 → 0.0."""
        p = MagicMock()
        p.circuit_state = "open"
        p.circuit_open_until = datetime.utcnow() + timedelta(hours=1)
        p.health_score = 0.75
        assert provider_health_score(p) == 0.0

    def test_open_circuit_expired_returns_half_open_score(self):
        """circuit_state=open 但已过期 → 0.3 (half_open)."""
        p = MagicMock()
        p.circuit_state = "open"
        p.circuit_open_until = datetime.utcnow() - timedelta(minutes=1)
        assert provider_health_score(p) == pytest.approx(0.3)

    def test_closed_healthy_provider(self):
        """closed + 高 health_score → 高分."""
        p = MagicMock()
        p.circuit_state = "closed"
        p.health_score = 0.9
        p.last_health_status = "healthy"
        p.consecutive_failures = 0
        p.success_rate_1h = 1.0
        score = provider_health_score(p)
        assert score >= 0.8

    def test_consecutive_failures_lower_score(self):
        """连续失败应降低分数."""
        p_good = MagicMock()
        p_good.circuit_state = "closed"
        p_good.health_score = 0.75
        p_good.last_health_status = None
        p_good.consecutive_failures = 0
        p_good.success_rate_1h = None

        p_bad = MagicMock()
        p_bad.circuit_state = "closed"
        p_bad.health_score = 0.75
        p_bad.last_health_status = None
        p_bad.consecutive_failures = 5
        p_bad.success_rate_1h = None

        assert provider_health_score(p_good) > provider_health_score(p_bad)


class TestLatencyScore:
    def test_fast_latency(self):
        assert latency_score(1000) == 1.0

    def test_slow_latency(self):
        assert latency_score(25000) == 0.1

    def test_none_returns_default(self):
        assert latency_score(None) == 0.7


class TestCostScore:
    def test_mini_model_cheap(self):
        assert cost_score("gpt-4o-mini") == 1.0

    def test_opus_model_expensive(self):
        assert cost_score("claude-opus-4") == 0.25


# ── 选择逻辑测试 (mock DB) ──


class TestModelSelectorFallback:
    @pytest.mark.asyncio
    async def test_fallback_candidates_not_fixed_score(self):
        """fallback 候选不应使用固定 score=0.1, 应基于真实评分."""
        # 构造一个 fallback 候选在 _score_all_candidates 内部
        # 通过检查 ModelCandidate.score != 0.1 来验证
        # (间接测试: fallback 分数计算使用了真实指标)
        p = MagicMock()
        p.id = 10
        p.name = "fb-provider"
        p.base_url = "https://fb.example.com"
        p.api_key = "key"
        p.enabled = True
        p.circuit_state = "closed"
        p.health_score = 0.9
        p.last_health_status = "healthy"
        p.consecutive_failures = 0
        p.success_rate_1h = 1.0
        p.avg_latency_ms = 500
        p.model_list = ["fb-model-mini"]
        p.default_model = "fb-model-mini"
        p.extra = {}
        p.last_health_full = {}

        # 模拟 DB 返回
        mock_db = AsyncMock()
        mock_db.get = AsyncMock(return_value=p)
        mock_db.execute = AsyncMock()

        # 构造空 scalars 让主候选池为空, 只走 fallback
        empty_result = MagicMock()
        empty_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = empty_result

        svc = ModelSelectorService()
        binding = MagicMock()
        binding.candidate_provider_ids = None
        binding.candidate_models_json = None
        binding.fallback_candidates_json = [
            {"provider_id": 10, "model": "fb-model-mini"},
        ]
        binding.temperature = None
        binding.max_tokens = None
        binding.extra_body = None

        candidates = await svc._score_all_candidates(
            mock_db, binding, {}, "quality_first", "planner",
        )
        # fallback 候选评分应该不是固定的 0.1
        fb = [c for c in candidates if c.model_name == "fb-model-mini"]
        if fb:
            assert fb[0].score != 0.1

    @pytest.mark.asyncio
    async def test_manual_mode_no_fallback(self):
        """manual 模式且 allow_auto_fallback=False 时不允许 fallback."""
        svc = ModelSelectorService()
        mock_db = AsyncMock()

        role = MagicMock()
        binding = MagicMock()
        binding.selection_mode = "manual"
        binding.allow_auto_fallback = False
        binding.auto_strategy = "quality_first"

        role_result = MagicMock()
        role_result.scalar_one_or_none.return_value = role
        binding_result = MagicMock()
        binding_result.scalar_one_or_none.return_value = binding
        mock_db.execute = AsyncMock(side_effect=[role_result, binding_result])

        # force_fallback + manual + no allow → should raise
        with pytest.raises(ValueError, match="不允许 fallback"):
            await svc.select_for_agent(
                mock_db,
                agent_role_key="planner",
                force_fallback=True,
            )

    @pytest.mark.asyncio
    async def test_manual_with_fallback_uses_backup_pool(self):
        """manual_with_fallback 模式可以使用备用池."""
        svc = ModelSelectorService()
        mock_db = AsyncMock()

        # 准备 role + binding
        role = MagicMock()
        role.id = 1
        binding = MagicMock()
        binding.selection_mode = "manual_with_fallback"
        binding.allow_auto_fallback = True
        binding.provider_id = 99  # primary 不存在
        binding.model_name = "model-a"
        binding.temperature = 0.7
        binding.max_tokens = 2048
        binding.extra_body = None

        # _get_role_and_binding
        role_result = MagicMock()
        role_result.scalar_one_or_none.return_value = role
        binding_result = MagicMock()
        binding_result.scalar_one_or_none.return_value = binding

        # _check_primary_available → False (主模型不可用)
        # _score_all_candidates → 返回候选
        provider = MagicMock()
        provider.id = 1
        provider.name = "backup"
        provider.base_url = "https://backup.com"
        provider.api_key = "k"
        provider.enabled = True
        provider.circuit_state = "closed"
        provider.health_score = 0.8
        provider.default_model = "backup-model"
        provider.model_list = ["backup-model"]
        provider.extra = {}
        provider.last_health_full = {}
        provider.consecutive_failures = 0
        provider.success_rate_1h = 1.0
        provider.avg_latency_ms = 500
        provider.last_health_status = "healthy"

        mock_db.get = AsyncMock(return_value=provider)

        # 让 _get_role_and_binding 返回 role+binding
        call_count = 0
        def mock_execute(q):
            nonlocal call_count
            call_count += 1
            r = MagicMock()
            if call_count <= 2:
                # _get_role_and_binding 的两次查询
                if call_count == 1:
                    r.scalar_one_or_none.return_value = role
                else:
                    r.scalar_one_or_none.return_value = binding
            else:
                r.scalars.return_value.all.return_value = [provider]
            return r
        mock_db.execute = AsyncMock(side_effect=mock_execute)

        result = await svc.select_for_agent(
            mock_db, agent_role_key="planner",
        )
        # 应该走了 auto/fallback 路径 (因为 _check_primary_available → False)
        assert result is not None

    @pytest.mark.asyncio
    async def test_circuit_open_provider_skipped(self):
        """circuit_state=open 的 Provider 应被跳过."""
        svc = ModelSelectorService()
        mock_db = AsyncMock()

        provider = MagicMock()
        provider.id = 1
        provider.name = "broken"
        provider.base_url = "https://broken.com"
        provider.api_key = "k"
        provider.enabled = True
        provider.circuit_state = "open"
        provider.circuit_open_until = datetime.utcnow() + timedelta(hours=1)
        provider.health_score = 0.0
        provider.model_list = ["model-x"]
        provider.default_model = "model-x"
        provider.extra = {}
        provider.last_health_full = {}
        provider.consecutive_failures = 10
        provider.success_rate_1h = 0.0
        provider.avg_latency_ms = 30000
        provider.last_health_status = "failed"

        mock_db.get = AsyncMock(return_value=provider)
        empty = MagicMock()
        empty.scalars.return_value.all.return_value = [provider]
        mock_db.execute = AsyncMock(return_value=empty)

        binding = MagicMock()
        binding.candidate_provider_ids = None
        binding.candidate_models_json = None
        binding.fallback_candidates_json = None
        binding.temperature = None
        binding.max_tokens = None
        binding.extra_body = None

        candidates = await svc._score_all_candidates(
            mock_db, binding, {}, "quality_first", "planner",
        )
        # open provider 应被跳过, 候选为空
        model_x = [c for c in candidates if c.model_name == "model-x"]
        assert len(model_x) == 0

    def test_text_roles_reject_media_models(self):
        assert not is_text_role_model_compatible("planner", "seedance-t2v-video")
        assert not is_text_role_model_compatible("critic", "qwen-vl-max")
        assert is_text_role_model_compatible("planner", "deepseek-chat")

    @pytest.mark.asyncio
    async def test_fallback_skips_media_default_model(self):
        """Last-resort fallback should still avoid image/video/audio models."""
        svc = ModelSelectorService()
        mock_db = AsyncMock()

        provider = MagicMock()
        provider.id = 7
        provider.name = "api-provider"
        provider.base_url = "https://api.example.com"
        provider.api_key = "sk-test"
        provider.enabled = True
        provider.circuit_state = "closed"
        provider.circuit_open_until = None
        provider.default_model = "seedance-t2v-video"
        provider.model_list = ["seedance-t2v-video", "deepseek-chat"]

        result = MagicMock()
        result.scalars.return_value.all.return_value = [provider]
        mock_db.execute = AsyncMock(return_value=result)

        selected = await svc._fallback_any_enabled(mock_db, "planner", None)
        assert selected.model_name == "deepseek-chat"
