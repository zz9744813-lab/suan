from __future__ import annotations

import pytest
from sqlalchemy import select


@pytest.mark.asyncio
async def test_llm_router_exact_cache_records_hit_and_request_id(monkeypatch, db):
    from app.core.database import init_db
    from app.models.model_call_event import ModelCallEvent
    from app.models.model_provider import ModelProvider
    from app.services.llm.client import LLMCallResult, LLMMessage
    from app.services.llm.router import LLMRouter, ResolvedCall

    await init_db()

    provider = ModelProvider(
        name="cache-provider",
        base_url="https://cache.example/v1",
        api_key="test-key",
        default_model="gpt-4o",
        model_list=["gpt-4o"],
        enabled=True,
    )
    db.add(provider)
    await db.flush()

    class CountingClient:
        def __init__(self) -> None:
            self.calls = 0

        async def chat(self, *, base_url, api_key, request, provider_extra):
            self.calls += 1
            return LLMCallResult(
                content=f"cached-content-{self.calls}",
                model=request.model,
                input_tokens=12,
                output_tokens=7,
                cost_usd=0.001,
                duration_ms=23,
                raw={"call": self.calls},
            )

    async def fake_resolve(self, db, role):
        fresh = await db.get(ModelProvider, provider.id)
        return ResolvedCall(
            provider=fresh,
            model="gpt-4o",
            temperature=0.2,
            max_tokens=128,
            selection_mode="manual",
        )

    monkeypatch.setattr(LLMRouter, "resolve", fake_resolve)
    client = CountingClient()
    router = LLMRouter(client)
    messages = [LLMMessage(role="user", content="same exact prompt")]

    _, first = await router.chat(db, "Draft", messages, stream=False)
    await db.commit()
    _, second = await router.chat(db, "Draft", messages, stream=False)
    await db.commit()

    assert client.calls == 1
    assert first.content == "cached-content-1"
    assert second.content == "cached-content-1"
    assert second.input_tokens == 0
    assert second.output_tokens == 0
    assert second.cost_usd == 0
    assert second.raw["_cache_hit"] is True

    events = (await db.execute(
        select(ModelCallEvent).order_by(ModelCallEvent.id.asc())
    )).scalars().all()
    assert [event.cache_hit for event in events] == [False, True]
    assert events[0].request_id
    assert events[0].request_id == events[1].request_id
