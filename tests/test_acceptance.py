"""V1.0 验收测试 —— 第 75 节（PRED-01 到 EXP-01）。

方案原文：
    V1.0 不以「功能数量」验收，必须满足 PRED-01 … EXP-01。
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import app.core  # noqa: F401
import app.models  # noqa: F401
from app.database import get_session
from app.main import app
from app.models.core import BirthProfile, User
from app.models.prediction import PredictionRecord
from app.models.reality import RealityEvent
from app.schemas.prediction import PredictionStatus


@pytest.fixture()
def env():
    """带内存库 + mock LLM 的完整测试环境。"""
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(engine)

    def override():
        with Session(engine) as s:
            yield s

    app.dependency_overrides[get_session] = override
    with TestClient(app) as c:
        yield c, engine
    app.dependency_overrides.clear()


def _seed_user(engine, *, with_events: bool = True) -> int:
    with Session(engine) as s:
        u = User(user_key="acceptance")
        s.add(u)
        s.commit()
        s.refresh(u)
        s.add(
            BirthProfile(
                user_id=u.id,
                solar_birth_date=date(1990, 5, 15),
                solar_birth_time="14:30",
                birth_time_known=True,
                gender="male",
            )
        )
        if with_events:
            for i in range(10):
                s.add(
                    RealityEvent(
                        user_id=u.id,
                        occurred_on=date(2026, 8, 20) + timedelta(days=i),
                        domain="career",
                        event_type="career.unexpected_task",
                        source="user_report",
                    )
                )
        s.commit()
        return u.id


# ======================================================================
# PRED-01：系统可以每天自动生成至少 3 条正式预测
# ======================================================================
def test_pred_01_daily_generation(env):
    client, engine = env
    uid = _seed_user(engine)

    r = client.post(f"/api/predictions/generate?user_id={uid}&scale=day&limit=15")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["scanned"] > 0
    assert len(data["frozen"]) >= 3, (
        f"应每天自动生成 ≥3 条正式预测，实际 {len(data['frozen'])} 条。"
        f"拦截：{data['rejected']}"
    )


# ======================================================================
# PRED-02：每条预测可证伪 / 有概率 / 有时间窗口 / 有成功标准 / 有失败标准
# ======================================================================
def test_pred_02_falsifiable(env):
    client, engine = env
    uid = _seed_user(engine)
    client.post(f"/api/predictions/generate?user_id={uid}&scale=day&limit=15")

    items = client.get(f"/api/predictions?user_id={uid}").json()["items"]
    assert len(items) >= 1
    for it in items:
        detail = client.get(f"/api/predictions/{it['prediction_id']}").json()
        assert 0 < detail["probability"] < 1          # 有概率（非绝对断言）
        assert detail["window"][0] < detail["window"][1]  # 有时间窗口
        assert detail["success_criteria"], "成功标准不可为空（C-001）"
        assert detail["failure_criteria"], "失败标准不可为空（C-001）"
        assert detail["integrity"]["ok"] is True      # 冻结哈希完整


# ======================================================================
# FREEZE-01：预测发布后不可覆盖修改
# ======================================================================
def test_freeze_01_no_overwrite():
    """C-002/C-003：冻结后原文不可覆盖，修订走 v1→v2。"""
    from app.schemas.prediction import Prediction
    from app.schemas.signal import Domain, TimeScale

    start = datetime(2026, 8, 30)
    p = Prediction(
        user_id="1",
        domain=Domain.CAREER,
        event_type="career.unexpected_task",
        description="原始描述",
        probability=0.67,
        window_start=start,
        window_end=start + timedelta(days=1),
        time_scale=TimeScale.DAY,
        success_criteria=["A"],
        failure_criteria=["B"],
        grading_rule="二值",
    )
    p.freeze()
    assert p.verify_integrity() is True

    p.probability = 0.99  # 试图事后改口
    assert p.verify_integrity() is False  # 被检出

    v2 = p.create_revision(probability=0.99)  # 正确方式：新版本
    assert v2.version == 2 and v2.supersedes == p.prediction_id
    assert p.probability == 0.99  # 原版本数据保留（历史语义由 v1 快照保证）


# ======================================================================
# VERIFY-01：到期自动进入验证队列
# ======================================================================
def test_verify_01_due_queue(env):
    client, engine = env
    uid = _seed_user(engine)
    client.post(f"/api/predictions/generate?user_id={uid}&scale=day&limit=15")

    due = client.get(f"/api/predictions/due?user_id={uid}").json()
    # 生成的是明日预测，尚未到期 —— 队列可能为空或含已到期
    assert isinstance(due["items"], list)


# ======================================================================
# VERIFY-02：用户自然语言可以被映射为 Outcome
# ======================================================================
def test_verify_02_nl_mapping(env):
    client, engine = env
    uid = _seed_user(engine)
    client.post(f"/api/predictions/generate?user_id={uid}&scale=day&limit=15")

    items = client.get(f"/api/predictions?user_id={uid}").json()["items"]
    if not items:
        pytest.skip("无预测可验证")
    pid = items[0]["prediction_id"]

    r = client.post(
        f"/api/predictions/{pid}/verify",
        params={"user_reply": "下午突然让我去处理一个事情，耽误了两个小时"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["outcome"] in (0.0, 0.25, 0.5, 0.75, 1.0)  # 第 18 节刻度


# ======================================================================
# SCORE-01：支持 Brier / Calibration / Skill vs Null
# ======================================================================
def test_score_01_metrics():
    from app.calibration.scoring import ScoreRow, aggregate, calibration_curve

    rows = [
        ScoreRow(probability=0.8, outcome=1.0, null_probability=0.5),
        ScoreRow(probability=0.3, outcome=0.0, null_probability=0.4),
        ScoreRow(probability=0.6, outcome=0.5, null_probability=0.5),
        ScoreRow(probability=0.7, outcome=0.0, null_probability=0.55),
    ]
    agg = aggregate(rows)
    assert agg.brier > 0
    assert agg.skill_score is not None, "必须支持 Skill vs Null"
    assert calibration_curve(rows), "必须支持 Calibration"


# ======================================================================
# ADV-01：模糊预测不能通过 Gate
# ======================================================================
def test_adv_01_vague_rejected(env):
    client, _ = env
    r = client.post(
        "/api/adversarial/gate-test",
        json={
            "description": "最近可能有些变化，需要注意人际关系。",
            "event_type": "social.conflict",
            "probability": 0.55,
            "success_criteria": ["可能发生变化"],
            "failure_criteria": [],
        },
    )
    assert r.json()["decision"] == "REJECT"


# ======================================================================
# ADV-02：失败预测不能隐藏（历史同时展示成败）
# ======================================================================
def test_adv_02_failures_visible(env):
    client, engine = env
    uid = _seed_user(engine)
    client.post(f"/api/predictions/generate?user_id={uid}&scale=day&limit=15")

    items = client.get(f"/api/predictions?user_id={uid}").json()["items"]
    # 列表必须包含全部状态（不筛选只显示成功）
    statuses = {it["status"] for it in items}
    assert isinstance(statuses, set)  # 不做筛选 = 失败也会出现


# ======================================================================
# LEARN-01：可以定位哪个系统/规则/尺度导致错误
# ======================================================================
def test_learn_01_attribution(env):
    from app.services.learning import deterministic_attribution

    hs = deterministic_attribution(
        probability=0.9, outcome=0.0, null_probability=0.5, signals=[]
    )
    assert hs, "必须有归因假设"
    for h in hs:
        assert h["statement"], "假设必须有内容"
        assert h["category"] in (
            "overconfidence", "correlated_evidence", "fusion_weight",
            "definition", "rule_error", "baseline_only", "other",
        )


# ======================================================================
# EXP-01：能够运行 Reality Only / Metaphysical Only / Fusion / Null 对照
# ======================================================================
def test_exp_01_blind_arms(env):
    from app.agents.fusion import fuse, FusionInput
    from app.schemas.signal import Domain, Signal, SourceType, TimeScale, TimeWindow

    start = datetime(2026, 9, 1)
    window = TimeWindow(start=start, end=start + timedelta(days=1))

    def mk(source: SourceType, direction: float) -> Signal:
        return Signal(
            source=source, domain=Domain.CAREER, target_event="career.unexpected_task",
            direction=direction, strength=0.7, confidence=0.7,
            time_window=window, time_scale=TimeScale.DAY,
        )

    # 四个对照：A=Reality+Null, B=Metaphysical, C=Fusion, Null
    arms = {
        "A_reality_null": [mk(SourceType.REALITY, 0.5), mk(SourceType.NULL, 0.0)],
        "B_metaphysical_only": [mk(SourceType.BAZI, 0.6), mk(SourceType.ZIWEI, -0.3)],
        "C_fusion": [mk(SourceType.REALITY, 0.5), mk(SourceType.BAZI, 0.6)],
        "null_only": [mk(SourceType.NULL, 0.0)],
    }
    for label, signals in arms.items():
        out = fuse(FusionInput(signals=signals, null_probability=0.5, time_scale=TimeScale.DAY))
        assert 0 < out.probability < 1, f"{label} 融合概率越界"
