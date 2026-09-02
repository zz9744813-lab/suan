"""命理批示缓存逻辑测试（第 6.1 节命盘解读）。

验证：批示算过一次后持久化，后续命中缓存（cached=True）不再实时调 LLM；
「重新生成」（refresh=true）才强制重算。
"""

from __future__ import annotations

from app.providers.base import LLMResponse


class _FakeProvider:
    """返回能解析出七维度批示的假 Provider，并记录调用次数。"""

    name = "fake"
    configured = True

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


class _FakeZiweiProvider:
    """返回能解析出六维度紫微批示的假 Provider。"""

    name = "fake"
    configured = True

    def __init__(self, calls: list):
        self._calls = calls

    def complete(self, request) -> LLMResponse:
        self._calls.append(request)
        return LLMResponse(
            content=(
                "命身总论：测试命身。\n"
                "事业官禄：测试官禄。\n"
                "财帛：测试财帛。\n"
                "夫妻感情：测试感情。\n"
                "迁移际遇：测试迁移。\n"
                "大限走势：测试大限。\n"
            ),
            model="fake-model",
            provider="fake",
            duration_ms=10,
        )


def test_ziwei_reading_cache(monkeypatch, client, user_id):
    """紫微批示：排盘（确定性）+ LLM 解读 + 缓存，与八字批示并列。"""
    calls: list = []
    monkeypatch.setattr(
        "app.providers.base.get_provider", lambda tier="reasoning": _FakeZiweiProvider(calls)
    )

    # 第一次：实时生成。chart 是确定性排盘，必须有十二宫
    r1 = client.get(f"/api/fortune/reading/ziwei?user_id={user_id}")
    assert r1.status_code == 200, r1.text
    d1 = r1.json()
    assert d1["cached"] is False
    assert d1["chart"] and len(d1["chart"]["palaces"]) == 12, d1.keys()
    assert d1["reading"] and d1["reading"].get("命身总论") == "测试命身。"
    assert len(calls) == 1

    # 第二次：命中缓存，不再调 LLM
    r2 = client.get(f"/api/fortune/reading/ziwei?user_id={user_id}")
    d2 = r2.json()
    assert d2["cached"] is True
    assert len(calls) == 1

    # 未知术式 → 404
    r3 = client.get(f"/api/fortune/reading/qimen?user_id={user_id}")
    assert r3.status_code == 404


def test_reading_falls_back_to_cheap_tier(monkeypatch, client, user_id):
    """reasoning 层整体故障（qiyovo deepseek 常见 500/挂起）时，批示自动回退 cheap 层。"""
    tried: list[str] = []

    def fake_get_provider(tier="reasoning"):
        tried.append(tier)
        if tier == "cheap":
            return _FakeProvider([])

        class _Failing:
            configured = True

            def complete(self, request) -> LLMResponse:
                return LLMResponse(content="", error="deepseek 500")

        return _Failing()

    monkeypatch.setattr("app.providers.base.get_provider", fake_get_provider)

    r = client.get(f"/api/fortune/reading?user_id={user_id}")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["reading"] and d["reading"]["命格总论"] == "测试命格。"
    assert tried == ["reasoning", "cheap"]


def test_reading_fallback_both_fail(monkeypatch, client, user_id):
    """两层都失败时：保留确定性盘面，错误信息明示双失败（前端降级展示）。"""
    tried: list[str] = []

    def fake_get_provider(tier="reasoning"):
        tried.append(tier)

        class _Failing:
            configured = True

            def complete(self, request) -> LLMResponse:
                return LLMResponse(content="", error=f"{tier} down")

        return _Failing()

    monkeypatch.setattr("app.providers.base.get_provider", fake_get_provider)

    r = client.get(f"/api/fortune/reading?user_id={user_id}")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["reading"] is None
    assert d["chart"]  # 确定性排盘仍然在
    assert "cheap" in d["error"] and "reasoning" in d["error"]
    assert tried == ["reasoning", "cheap"]
