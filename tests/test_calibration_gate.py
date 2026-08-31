"""校准阶段门槛（Calibration Gate）测试。

验证三阶段治本方案：
    cold   （< MIN_CALIBRATION_SAMPLES）：术式不参与融合，产出 p=Null 的研究样本；
    explore（< MIN_FORMAL_SAMPLES）    ：术式以弱先验参与融合并留痕，产出仍为
                                         RESEARCH（不代表预测力），为每术式积累实证；
    formal （≥ MIN_FORMAL_SAMPLES）    ：edge 门槛 + 对抗 Gate + 学习到的融合权重。

对应 config：MIN_CALIBRATION_SAMPLES / MIN_FORMAL_SAMPLES / RESEARCH_SAMPLE_LIMIT。
"""

from __future__ import annotations

import pytest


@pytest.fixture()
def _real_gates(monkeypatch):
    """恢复真实校准门槛（覆盖 conftest 的 autouse 禁用）。"""
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "MIN_CALIBRATION_SAMPLES", 5)
    monkeypatch.setattr(get_settings(), "MIN_FORMAL_SAMPLES", 20)
    monkeypatch.setattr(get_settings(), "RESEARCH_SAMPLE_LIMIT", 3)
    monkeypatch.setattr(get_settings(), "MIN_PREDICTION_EDGE", 0.03)


def _verified_count(client, user_id: int) -> int:
    """已验证样本数（prediction_scores）——analytics.overall 的 sample_size。"""
    resp = client.get(f"/api/analytics/overall?user_id={user_id}")
    assert resp.status_code == 200, resp.text
    return int(resp.json().get("sample_size") or 0)


def _generate(client, user_id: int) -> dict:
    resp = client.post(f"/api/predictions/generate?user_id={user_id}&scale=day&limit=20")
    assert resp.status_code == 200, resp.text
    return resp.json()


def _verify_all_pending(client, user_id: int) -> int:
    """把当前可见的全部待验证预测标为「命中」（quick_answer=A），返回验证条数。"""
    items = client.get(f"/api/predictions?user_id={user_id}").json()["items"]
    pending = [
        it for it in items
        if it["status"] in ("RESEARCH", "FROZEN", "VERIFY_REQUIRED", "WAITING_USER")
    ]
    for it in pending:
        r = client.post(
            f"/api/predictions/{it['prediction_id']}/verify",
            params={"quick_answer": "A"},
        )
        assert r.status_code == 200, r.text
    return len(pending)


def _accumulate_verified(client, user_id: int, target: int) -> None:
    """反复 生成 → 验证，直到已验证样本数达到 target。"""
    for _ in range(12):  # 每轮最多 RESEARCH_SAMPLE_LIMIT(3) 条，留足轮次余量
        if _verified_count(client, user_id) >= target:
            return
        _generate(client, user_id)
        _verify_all_pending(client, user_id)
    assert _verified_count(client, user_id) >= target, (
        f"样本积累失败：{_verified_count(client, user_id)} < {target}"
    )


# ======================================================================
# cold 阶段（< MIN_CALIBRATION_SAMPLES）
# ======================================================================

def test_cold_start_produces_research_samples(client, user_id, _real_gates):
    """冷启动：产出 RESEARCH 研究样本，不产出 FROZEN 正式预测。"""
    data = _generate(client, user_id)

    # notes 必须诚实说明冷启动
    assert any("冷启动" in n for n in data["notes"]), data["notes"]

    # 冻结的必须是研究样本（frozen 列表可见，但 status 需查库确认）
    assert len(data["frozen"]) > 0, "冷启动应产出研究样本以启动校准闭环"

    # 查库：status 应为 RESEARCH（而非 FROZEN）
    lst = client.get(f"/api/predictions?user_id={user_id}").json()
    items = lst["items"]
    assert items, "研究样本应可见（供用户验证）"
    assert all(it["status"] == "RESEARCH" for it in items), items


def test_cold_start_respects_sample_limit(client, user_id, _real_gates):
    """冷启动：研究样本数不超过 RESEARCH_SAMPLE_LIMIT。"""
    data = _generate(client, user_id)
    assert len(data["frozen"]) <= 3, data["frozen"]


def test_cold_start_probability_equals_null(client, user_id, _real_gates):
    """冷启动：研究样本概率 = Null 基线（术式未参与融合）。"""
    _generate(client, user_id)
    items = client.get(f"/api/predictions?user_id={user_id}").json()["items"]
    for it in items:
        assert it["status"] == "RESEARCH"
        # 研究样本 probability 应等于 null_probability（术式不产生偏移）
        assert it["null_probability"] is not None
        assert abs(it["probability"] - it["null_probability"]) < 1e-6, it


# ======================================================================
# explore 阶段（MIN_CALIBRATION_SAMPLES ≤ n < MIN_FORMAL_SAMPLES）
# ======================================================================

def test_explore_phase_includes_metaphysical_signals(client, user_id, _real_gates):
    """实证期：术式信号恢复参与（弱先验），但产出仍是 RESEARCH 研究样本。

    这是 5~19 样本空窗的治本点：既不让未实证术式的噪声冒充正式预测，
    又让各术式信号完整留痕 —— 验证后可为每个源积累实证样本，
    喂养可靠度矩阵（source_types 落库），学习闭环不再空转。
    """
    _accumulate_verified(client, user_id, 5)

    data = _generate(client, user_id)
    assert any("实证期" in n for n in data["notes"]), data["notes"]
    assert data["frozen"], "实证期应继续产出研究样本"

    # 仍为 RESEARCH（不是正式预测），但信号里已有术式源（不再只有 null）
    items = client.get(f"/api/predictions?user_id={user_id}").json()["items"]
    new_ids = {f["prediction_id"] for f in data["frozen"]}
    new_items = [it for it in items if it["prediction_id"] in new_ids]
    assert new_items and all(it["status"] == "RESEARCH" for it in new_items), new_items

    detail = client.get(f"/api/predictions/{new_items[0]['prediction_id']}").json()
    sources = {s["source"] for s in detail["signals"]}
    assert "null" in sources
    assert sources - {"null", "reality"}, f"实证期应包含术式信号，实际 {sources}"


# ======================================================================
# formal 阶段（≥ MIN_FORMAL_SAMPLES）
# ======================================================================

def test_formal_phase_after_threshold(client, user_id, _real_gates):
    """正式期：达到 MIN_FORMAL_SAMPLES 后，系统恢复正式预测流程。"""
    _accumulate_verified(client, user_id, 20)

    data = _generate(client, user_id)
    # 不再处于研究期：notes 不应出现冷启动/实证期，应进入预算竞争或诚实拒绝
    assert not any("冷启动" in n or "实证期" in n for n in data["notes"]), data["notes"]
    assert any(
        "预算竞争" in n or "NO_EDGE" in str(data["rejected"]) for n in data["notes"] + [""]
    ) or data["rejected"], data


def test_verify_writes_source_types(client, user_id, _real_gates):
    """验证后评分必须记录 source_types —— 可靠度矩阵按源学习的依据（第 26 节）。"""
    _generate(client, user_id)
    items = client.get(f"/api/predictions?user_id={user_id}").json()["items"]
    assert items
    pid = items[0]["prediction_id"]

    r = client.post(f"/api/predictions/{pid}/verify", params={"quick_answer": "A"})
    assert r.status_code == 200, r.text

    # 可靠度矩阵应能看到 non-empty 的 by_source（score 带上了源信息）
    rel = client.get(f"/api/analytics/reliability?user_id={user_id}")
    assert rel.status_code == 200, rel.text
    by_system = rel.json().get("by_system", [])
    assert by_system, "验证后 by_source 不应为空（source_types 必须落库）"


def test_fusion_weights_unproven_sources_weak_prior():
    """未实证源 = 弱先验 0.5（禁止 6），不再按 1.0 全可信参与融合。"""
    from app.learning.reliability import ReliabilityMatrix
    from sqlalchemy import create_engine
    from sqlalchemy.pool import StaticPool
    from sqlmodel import Session, SQLModel

    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        weights = ReliabilityMatrix(session).fusion_weights()

    assert weights, "应对所有已知源给出权重"
    assert all(w == 0.5 for w in weights.values()), weights
