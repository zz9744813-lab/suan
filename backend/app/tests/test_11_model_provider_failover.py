"""L7 test_11_model_provider_failover.py — 模型路由 fallback 契约。"""
from __future__ import annotations

import pytest


class NoopRecorder:
    async def record_selection(self, *args, **kwargs):
        return {"event": "selection"}

    async def record_success(self, *args, **kwargs):
        return None

    async def record_failure(self, *args, **kwargs):
        return None

    async def record_fallback_success(self, *args, **kwargs):
        return None


class NoopCircuitBreaker:
    async def record_failure(self, *args, **kwargs):
        return None


async def make_provider(db, *, name: str, model: str):
    from app.models.model_provider import ModelProvider

    provider = ModelProvider(
        name=name,
        base_url=f"https://{name}.example/v1",
        api_key="test-key",
        default_model=model,
        model_list=[model],
        enabled=True,
        health_score=1.0,
    )
    db.add(provider)
    await db.flush()
    await db.commit()
    return provider


@pytest.mark.asyncio
class TestModelProviderFailover:
    async def test_manual_lock_does_not_fallback(self, monkeypatch, db):
        from app.models.model_provider import ModelProvider
        from app.services.llm import router as router_module
        from app.services.llm.client import LLMAuthError, LLMMessage
        from app.services.llm.router import LLMRouter, ResolvedCall

        provider = await make_provider(db, name="manual-provider", model="gpt-4o")
        calls = {"fallback": 0}

        class FailingClient:
            async def chat(self, **kwargs):
                raise LLMAuthError("401")

        async def fake_resolve(self, db, role):
            fresh = await db.get(ModelProvider, provider.id)
            return ResolvedCall(
                provider=fresh,
                model="gpt-4o",
                temperature=0.2,
                max_tokens=128,
                selection_mode="manual",
            )

        async def fake_try_fallback(self, *args, **kwargs):
            calls["fallback"] += 1
            return None

        monkeypatch.setattr(router_module, "ModelCallRecorder", lambda: NoopRecorder())
        monkeypatch.setattr("app.services.model_circuit_breaker.CircuitBreakerService", lambda: NoopCircuitBreaker())
        monkeypatch.setattr(LLMRouter, "resolve", fake_resolve)
        monkeypatch.setattr(LLMRouter, "_try_fallback", fake_try_fallback)

        llm_router = LLMRouter(FailingClient())
        with pytest.raises(Exception):
            await llm_router.chat(db, "Draft", [LLMMessage(role="user", content="hi")], stream=False)
        assert calls["fallback"] == 0

    async def test_manual_with_fallback_uses_candidate(self, monkeypatch, db):
        from app.models.model_provider import ModelProvider
        from app.services.llm import router as router_module
        from app.services.llm.client import LLMAuthError, LLMCallResult, LLMMessage
        from app.services.llm.router import LLMRouter, ResolvedCall

        primary = await make_provider(db, name="primary-provider", model="gpt-4o")
        fallback = await make_provider(db, name="fallback-provider", model="gpt-4o-mini")
        calls = []

        class FallbackClient:
            async def chat(self, *, base_url, api_key, request, provider_extra):
                calls.append((base_url, request.model))
                if request.model == "gpt-4o":
                    raise LLMAuthError("401")
                return LLMCallResult(
                    content="ok",
                    raw={"choices": []},
                    input_tokens=1,
                    output_tokens=1,
                    cost_usd=0.0,
                    duration_ms=1,
                    model=request.model,
                )

        async def fake_resolve(self, db, role):
            fresh = await db.get(ModelProvider, primary.id)
            return ResolvedCall(
                provider=fresh,
                model="gpt-4o",
                temperature=0.2,
                max_tokens=128,
                selection_mode="manual_with_fallback",
            )

        async def fake_try_fallback(self, db, role, agent_key, messages, **kwargs):
            fresh = await db.get(ModelProvider, fallback.id)
            resolved = ResolvedCall(
                provider=fresh,
                model="gpt-4o-mini",
                temperature=0.2,
                max_tokens=128,
                selection_mode="manual_with_fallback",
                selection_reason="fallback#1",
            )
            result = await self.client.chat(
                base_url=fresh.base_url,
                api_key=fresh.api_key,
                request=router_module.LLMRequest(
                    model=resolved.model,
                    messages=messages,
                    temperature=resolved.temperature,
                    max_tokens=resolved.max_tokens,
                    stream=False,
                ),
                provider_extra={},
            )
            return resolved, result

        monkeypatch.setattr(router_module, "ModelCallRecorder", lambda: NoopRecorder())
        monkeypatch.setattr("app.services.model_circuit_breaker.CircuitBreakerService", lambda: NoopCircuitBreaker())
        monkeypatch.setattr(LLMRouter, "resolve", fake_resolve)
        monkeypatch.setattr(LLMRouter, "_try_fallback", fake_try_fallback)

        llm_router = LLMRouter(FallbackClient())
        resolved, result = await llm_router.chat(db, "Draft", [LLMMessage(role="user", content="hi")], stream=False)
        assert resolved.provider.id == fallback.id
        assert resolved.model == "gpt-4o-mini"
        assert result.content == "ok"
        assert calls == [
            (primary.base_url, "gpt-4o"),
            (fallback.base_url, "gpt-4o-mini"),
        ]
