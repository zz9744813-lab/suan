"""命理批示缓存逻辑测试（第 6.1 节命盘解读）。

验证：批示算过一次后持久化，后续命中缓存（cached=True）不再实时调 LLM；
「重新生成」（refresh=true）才强制重算。
"""

from __future__ import annotations

from app.providers.base import LLMResponse


class _FakeProvider:
    """返回能解析出七维度批示的假 Provider，并记录调用次数。"""

    name = "fake"

    def __init__(self, calls: list):
        self._calls = calls

    def complete(self, request) -> LLMResponse:
        self._calls.append(request)
        return LLMResponse(
            content=(
                "命格总论：测试命格。\n"
                "事业：测试事业。\n"
                "财运：测试财运。\n"
                "婚恋：测试婚恋。\n"
                "健康：测试健康。\n"
                "未来5年：测试五年。\n"
                "未来10年：测试十年。\n"
            ),
            model="fake-model",
            provider="fake",
            duration_ms=10,
        )


def test_fortune_reading_cache(monkeypatch, client, user_id):
    calls: list = []
    monkeypatch.setattr(
        "app.providers.base.get_provider", lambda tier="reasoning": _FakeProvider(calls)
    )

    # 第一次：实时生成，落库
    r1 = client.get(f"/api/fortune/reading?user_id={user_id}")
    assert r1.status_code == 200, r1.text
    d1 = r1.json()
    assert d1["cached"] is False
    assert d1["reading"] and d1["reading"].get("命格总论") == "测试命格。"
    assert len(calls) == 1

    # 第二次：命中缓存，不再调 LLM
    r2 = client.get(f"/api/fortune/reading?user_id={user_id}")
    assert r2.status_code == 200, r2.text
    d2 = r2.json()
    assert d2["cached"] is True
    assert d2["reading"].get("命格总论") == "测试命格。"
    assert len(calls) == 1  # 没有新增调用

    # refresh=true：强制重算
    r3 = client.get(f"/api/fortune/reading?user_id={user_id}&refresh=true")
    assert r3.status_code == 200, r3.text
    d3 = r3.json()
    assert d3["cached"] is False
    assert len(calls) == 2

    # 重算后再查：又命中缓存
    r4 = client.get(f"/api/fortune/reading?user_id={user_id}")
    assert r4.json()["cached"] is True
    assert len(calls) == 2
