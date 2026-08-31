"""冷启动校准门槛（Calibration Gate）测试。

验证治本方案：
    零验证样本时，术式信号未经实证不参与融合，系统产出 RESEARCH 研究样本
    而非 FROZEN 正式预测，避免「噪声偶然偏离 Null」产出假预测误导用户。

对应 config：MIN_CALIBRATION_SAMPLES / RESEARCH_SAMPLE_LIMIT。
"""

from __future__ import annotations

import pytest


@pytest.fixture()
def _cold_start(monkeypatch):
    """恢复真实冷启动门槛（覆盖 conftest 的 autouse 禁用）。"""
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "MIN_CALIBRATION_SAMPLES", 5)
    monkeypatch.setattr(get_settings(), "RESEARCH_SAMPLE_LIMIT", 3)
    monkeypatch.setattr(get_settings(), "MIN_PREDICTION_EDGE", 0.03)


def test_cold_start_produces_research_samples(client, user_id, _cold_start):
    """冷启动：产出 RESEARCH 研究样本，不产出 FROZEN 正式预测。"""
    resp = client.post(f"/api/predictions/generate?user_id={user_id}&scale=day&limit=20")
    assert resp.status_code == 200, resp.text
    data = resp.json()

    # notes 必须诚实说明冷启动
    assert any("冷启动" in n for n in data["notes"]), data["notes"]

    # 冻结的必须是研究样本（frozen 列表可见，但 status 需查库确认）
    assert len(data["frozen"]) > 0, "冷启动应产出研究样本以启动校准闭环"

    # 查库：status 应为 RESEARCH（而非 FROZEN）
    lst = client.get(f"/api/predictions?user_id={user_id}").json()
    items = lst["items"]
    assert items, "研究样本应可见（供用户验证）"
    assert all(it["status"] == "RESEARCH" for it in items), items


def test_cold_start_respects_sample_limit(client, user_id, _cold_start):
    """冷启动：研究样本数不超过 RESEARCH_SAMPLE_LIMIT。"""
    resp = client.post(f"/api/predictions/generate?user_id={user_id}&scale=day&limit=20")
    data = resp.json()
    assert len(data["frozen"]) <= 3, data["frozen"]


def test_cold_start_probability_equals_null(client, user_id, _cold_start):
    """冷启动：研究样本概率 = Null 基线（术式未参与融合）。"""
    client.post(f"/api/predictions/generate?user_id={user_id}&scale=day&limit=20")
    items = client.get(f"/api/predictions?user_id={user_id}").json()["items"]
    for it in items:
        assert it["status"] == "RESEARCH"
        # 研究样本 probability 应等于 null_probability（术式不产生偏移）
        assert it["null_probability"] is not None
        assert abs(it["probability"] - it["null_probability"]) < 1e-6, it
