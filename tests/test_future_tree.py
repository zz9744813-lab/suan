"""Future Tree 与 Counterfactual 测试 —— 第 27 / 28 节。"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import app.models  # noqa: F401
from app.models.core import User
from app.models.reality import DailyState, RealityEvent


@pytest.fixture()
def session():
    e = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(e)
    with Session(e) as s:
        u = User(user_key="ft")
        s.add(u)
        s.commit()
        s.refresh(u)
        # 30 天学习趋势：上升
        for i in range(30):
            d = date(2026, 8, 1) + timedelta(days=i)
            s.add(
                DailyState(
                    user_id=u.id,
                    state_date=d,
                    state={"study": {"minutes": 30 + i}},
                    study_minutes=30 + i,
                    active_projects=2,
                    event_count=3,
                )
            )
        # career 事件占比高
        for i in range(15):
            s.add(
                RealityEvent(
                    user_id=u.id,
                    occurred_on=date(2026, 8, 5) + timedelta(days=i),
                    domain="career",
                    event_type="career.unexpected_task",
                )
            )
        s.add(
            RealityEvent(
                user_id=u.id,
                occurred_on=date(2026, 8, 10),
                domain="study",
                event_type="study.study_session",
            )
        )
        s.commit()
        yield s


def test_future_tree_deterministic(session):
    """第 27 节：同数据同结果。"""
    from app.services.future_tree import FutureTreeBuilder

    a = FutureTreeBuilder(session, user_id=1).build(as_of=date(2026, 8, 31))
    b = FutureTreeBuilder(session, user_id=1).build(as_of=date(2026, 8, 31))
    assert a["scenarios"] == b["scenarios"]


def test_future_tree_structure(session):
    """第 27 节：三个情景 + 概率归一化。"""
    from app.services.future_tree import FutureTreeBuilder

    tree = FutureTreeBuilder(session, user_id=1).build(as_of=date(2026, 8, 31))
    assert len(tree["scenarios"]) == 3
    total = sum(s["probability"] for s in tree["scenarios"])
    assert abs(total - 1.0) < 0.01
    keys = {s["key"] for s in tree["scenarios"]}
    assert keys == {"A", "B", "C"}


def test_future_tree_changes_with_evidence(session):
    """第 27 节：新证据 → 概率重算（不同输入 → 不同结果）。"""
    from app.services.future_tree import FutureTreeBuilder

    builder = FutureTreeBuilder(session, user_id=1)
    # 无 career 事件的新用户（空库）应给出不同分布
    with Session(session.bind) as s2:
        u2 = User(user_key="ft2")
        s2.add(u2)
        s2.commit()
        tree_empty = builder.build(as_of=date(2026, 8, 31), )
        # 用同一 builder 但 user_id=2 无数据
        from app.services.future_tree import FutureTreeBuilder as FTB

        empty = FTB(s2, user_id=u2.id).build(as_of=date(2026, 8, 31))
        assert empty["scenarios"] != tree_empty["scenarios"]


def test_counterfactual_baseline_vs_intervention(session):
    """第 28 节：干预应提升对应维度强度。"""
    from app.services.counterfactual import CounterfactualEngine

    result = CounterfactualEngine(session, user_id=1).compare(
        interventions=[{"label": "每天学习1小时", "effects": {"study": 0.4}}],
        as_of=date(2026, 8, 31),
    )
    scenarios = {s["key"]: s for s in result["scenarios"]}
    assert "baseline" in scenarios
    assert "intervention_1" in scenarios

    base_study = scenarios["baseline"]["dimensions"]["study"]
    iv_study = scenarios["intervention_1"]["dimensions"]["study"]
    assert iv_study > base_study, "干预应提升学习强度"


def test_counterfactual_returns_multiple_interventions(session):
    from app.services.counterfactual import CounterfactualEngine

    result = CounterfactualEngine(session, user_id=1).compare(
        interventions=[
            {"label": "每天学习", "effects": {"study": 0.3}},
            {"label": "停止刷手机", "effects": {"study": 0.2, "social": -0.1}},
        ],
        as_of=date(2026, 8, 31),
    )
    assert len(result["scenarios"]) == 3  # baseline + 2 interventions
