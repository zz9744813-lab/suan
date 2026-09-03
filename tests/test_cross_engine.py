"""多方法交叉扫描 / 叙事重建 / 今日锦囊测试。

对应原则：
- C-001：description 保持「何时+何事」短断言（Gate 友好）；
  叙事是读取端展示层（deterministic 重建）。
- C-005：引擎交叉只影响「选什么事 + 怎么说」，不动概率权威。
- C-006 / 禁止 6：交叉印证数只是信号事实陈述，概率仍为 Null/融合。
"""

from __future__ import annotations

from datetime import date


def test_daily_almanac_deterministic_and_complete(client, user_id):
    """今日锦囊：宜忌/吉神方位/幸运色数/吉时齐备，且同日两次一致。"""
    r1 = client.get(f"/api/fortune/daily?user_id={user_id}&date=2026-09-03")
    assert r1.status_code == 200, r1.text
    d1 = r1.json()
    assert d1["day_ganzhi"] and d1["yi"] and d1["ji"]
    assert d1["xi_dir"] and d1["cai_dir"] and d1["fu_dir"]
    assert d1["lucky_color"] and d1["lucky_numbers"]
    assert d1["lucky_hours"], "应有吉时"
    assert d1.get("day_master"), "有出生档案时应给出日主"
    assert "peach_blossom_stars" in d1

    r2 = client.get(f"/api/fortune/daily?user_id={user_id}&date=2026-09-03")
    assert r2.json() == d1

    # 无日期参数 → 默认今天
    r3 = client.get(f"/api/fortune/daily?user_id={user_id}")
    assert r3.status_code == 200
    assert r3.json()["date"] == date.today().isoformat()


def test_romance_events_in_ontology(client):
    """姻缘类事件已进入本体（正缘/推进/波折），且保持可证伪。"""
    r = client.get("/api/ontology/events")
    if r.status_code == 404:
        # 无该接口也能验证本体本身
        from app.prediction.ontology import ONTOLOGY

        spec = ONTOLOGY.get("relationship.romantic_encounter")
    else:
        items = r.json().get("events", r.json())
        spec = None
        for e in items if isinstance(items, list) else []:
            if e.get("event_type") == "relationship.romantic_encounter":
                spec = e
                break
    assert spec, "本体应包含 relationship.romantic_encounter"
    succ = spec["success_criteria"] if isinstance(spec, dict) else spec.success_criteria
    fail = spec["failure_criteria"] if isinstance(spec, dict) else spec.failure_criteria
    assert succ and fail


def test_research_samples_carry_signals_and_narrative(client, user_id):
    """研究样本：不再只有 Null —— 术式信号参与选题留痕，叙事项齐备。"""
    r = client.post(f"/api/predictions/generate?user_id={user_id}")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["frozen"], f"应产出研究样本：{d.get('notes')}"

    items = client.get(f"/api/predictions?user_id={user_id}").json()["items"]
    assert items
    with_mixed_sources = [
        it for it in items if it.get("supporting_sources") or it.get("opposing_sources")
    ]
    assert with_mixed_sources, "研究样本应带有术式信号来源标记（交叉信息）"

    with_narrative = [it for it in items if it.get("narrative")]
    assert with_narrative, "列表应携带叙事"
    sample = with_narrative[0]
    assert "建议：" in sample["narrative"]
    assert ("多法印证" in sample["narrative"]) or ("各术式无明显同向" in sample["narrative"])

    # description 仍是「何时+何事」短断言（Gate 友好、C-001）
    assert "。" in sample["description"] and len(sample["description"]) < 60


def test_narrative_rebuild_is_deterministic(client, user_id):
    """同一预测的叙事重复读取逐字相同（可重建而非落库）。"""
    client.post(f"/api/predictions/generate?user_id={user_id}")
    items = client.get(f"/api/predictions?user_id={user_id}").json()["items"]
    assert items
    pid = items[0]["prediction_id"]
    n1 = client.get(f"/api/predictions/{pid}").json()["narrative"]
    n2 = client.get(f"/api/predictions/{pid}").json()["narrative"]
    assert n1 == n2 and n1
