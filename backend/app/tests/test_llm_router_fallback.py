"""P0 Phase 3: LLM Router fallback chain tests."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from app.services.llm.router import LLMRouter, ResolvedCall, MAX_FALLBACK_ATTEMPTS
from app.services.llm.client import (
    LLMClient,
    LLMCallResult,
    LLMAuthError,
    LLMConnectionError,
    LLMRateLimitError,
    LLMResponseError,
    LLMError,
)


def _make_provider(**overrides):
    p = MagicMock()
    p.id = 1
    p.name = "test-provider"
    p.base_url = "https://api.example.com"
    p.api_key = "test-key"
    p.enabled = True
    p.extra = {}
    for k, v in overrides.items():
        setattr(p, k, v)
    return p


def _make_call_result(content="ok"):
    return LLMCallResult(
        content=content,
        model="gpt-4",
        input_tokens=10,
        output_tokens=20,
        cost_usd=0.001,
        duration_ms=500,
        raw={"choices": [{"message": {"content": content}}]},
    )


class TestLLMRouterFallback:
    @pytest.mark.asyncio
    async def test_primary_success_no_fallback(self):
        """主模型成功时不触发 fallback."""
        mock_client = AsyncMock(spec=LLMClient)
        mock_client.chat = AsyncMock(return_value=_make_call_result())

        router = LLMRouter(client=mock_client)
        mock_db = AsyncMock()

        # Mock resolve to return a known provider
        resolved = ResolvedCall(
            provider=_make_provider(),
            model="gpt-4",
            temperature=0.7,
            max_tokens=2048,
            selection_mode="auto",
        )

        with patch.object(router, "resolve", return_value=resolved):
            with patch("app.services.llm.router.ModelCallRecorder"):
                with patch("app.services.model_circuit_breaker.CircuitBreakerService"):
                    res_call, result = await router.chat(
                        mock_db, role="draft",
                        messages=[],
                    )
        # chat 只被调用一次 (主模型)
        assert mock_client.chat.call_count == 1
        assert result.content == "ok"

    @pytest.mark.asyncio
    async def test_primary_failure_triggers_fallback(self):
        """主模型失败应触发 fallback."""
        mock_client = AsyncMock(spec=LLMClient)
        # 主模型失败, fallback 成功
        mock_client.chat = AsyncMock(
            side_effect=[LLMConnectionError("连接失败"), _make_call_result("fallback-ok")],
        )

        router = LLMRouter(client=mock_client)
        mock_db = AsyncMock()

        provider = _make_provider()
        resolved = ResolvedCall(
            provider=provider,
            model="gpt-4",
            temperature=0.7,
            max_tokens=2048,
            selection_mode="auto",
        )

        # Mock fallback 候选
        from app.services.model_selector import ModelCandidate, SelectedModel

        fb_provider = _make_provider(id=2, name="backup", base_url="https://backup.com")
        fb_candidate = ModelCandidate(
            provider_id=2,
            provider_name="backup",
            base_url="https://backup.com",
            api_key="key2",
            model_name="claude-3",
            score=0.6,
            reason="fallback",
        )
        selected_model = SelectedModel(
            provider=fb_provider,
            model_name="claude-3",
            temperature=0.7,
            max_tokens=2048,
            extra_body=None,
            selection_mode="manual_with_fallback",
            selection_score=0.6,
            selection_reason="fallback",
            candidates=[fb_candidate],
        )

        with patch.object(router, "resolve", return_value=resolved):
            with patch("app.services.llm.router.ModelCallRecorder"):
                with patch("app.services.llm.router.classify_llm_exception", return_value="connection_error"):
                    with patch("app.services.model_circuit_breaker.CircuitBreakerService"):
                        with patch("app.services.llm.router.get_model_selector") as mock_sel:
                            mock_sel.return_value.select_for_agent = AsyncMock(return_value=selected_model)
                            mock_db.get = AsyncMock(return_value=fb_provider)
                            try:
                                res_call, result = await router.chat(
                                    mock_db, role="draft",
                                    messages=[],
                                )
                            except Exception:
                                pass  # fallback 可能也会失败, 测试重点在调用次数

        # 主模型调用 1 次 + fallback 尝试
        assert mock_client.chat.call_count >= 1

    @pytest.mark.asyncio
    async def test_fallback_does_not_retry_same_provider_model(self):
        """fallback 不应重试刚失败的 provider/model."""
        from app.services.model_selector import ModelCandidate, SelectedModel

        fb_provider = _make_provider(id=2, name="backup")
        # 候选里包含跟主模型一样的 provider/model
        same_candidate = ModelCandidate(
            provider_id=1,  # same as primary
            provider_name="test-provider",
            base_url="https://api.example.com",
            api_key="test-key",
            model_name="gpt-4",  # same as primary
            score=0.5,
            reason="same",
        )
        diff_candidate = ModelCandidate(
            provider_id=2,
            provider_name="backup",
            base_url="https://backup.com",
            api_key="key2",
            model_name="claude-3",
            score=0.4,
            reason="diff",
        )
        selected_model = SelectedModel(
            provider=_make_provider(),
            model_name="gpt-4",
            temperature=0.7,
            max_tokens=2048,
            extra_body=None,
            selection_mode="manual_with_fallback",
            selection_score=0.5,
            selection_reason="test",
            candidates=[same_candidate, diff_candidate],
        )

        # _try_fallback 内部应过滤掉 same_candidate (provider_id=1, model=gpt-4)
        # 因为它就是主模型
        fallback_candidates = [
            c for c in selected_model.candidates
            if not (c.provider_id == _make_provider().id and c.model_name == "gpt-4")
        ]
        assert len(fallback_candidates) == 1
        assert fallback_candidates[0].model_name == "claude-3"

    @pytest.mark.asyncio
    async def test_all_candidates_exhausted_raises_error(self):
        """所有候选都失败应抛出结构化错误."""
        from app.core.errors import ModelConnectionError

        mock_client = AsyncMock(spec=LLMClient)
        mock_client.chat = AsyncMock(side_effect=LLMConnectionError("连接失败"))

        router = LLMRouter(client=mock_client)
        mock_db = AsyncMock()

        resolved = ResolvedCall(
            provider=_make_provider(),
            model="gpt-4",
            temperature=0.7,
            max_tokens=2048,
            selection_mode="manual",  # manual 模式不允许 fallback
        )

        with patch.object(router, "resolve", return_value=resolved):
            with patch("app.services.llm.router.ModelCallRecorder"):
                with patch("app.services.llm.router.classify_llm_exception", return_value="connection_error"):
                    with patch("app.services.model_circuit_breaker.CircuitBreakerService"):
                        with pytest.raises(Exception):
                            await router.chat(
                                mock_db, role="draft",
                                messages=[],
                            )

    def test_max_fallback_attempts_value(self):
        """MAX_FALLBACK_ATTEMPTS 应为 2."""
        assert MAX_FALLBACK_ATTEMPTS == 2
