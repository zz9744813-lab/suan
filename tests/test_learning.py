"""学习闭环测试 —— 第 22/23/24/25/26/33 节。"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import app.models  # noqa: F401
from app.models.core import User
from app.models.prediction import PredictionRecord, SignalRecord
from app.models.registry import RuleMetric
from app.models.scoring import PredictionScore
from app.schemas.prediction import PredictionStatus


@pytest.fixture()
def session():
    e = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(e)
    with Session(e) as s:
        yield s


def _seed(session: Session, *, probability: float = 0.8, outcome: float = 0.0,
          null_prob: float = 0.5, rule: str = "BAZI-R-test", pid: str = "P-LEARN-1") -> str:
    existing_user = session.exec(
        select(User).where(User.user_key == "learner")
    ).first()
    if existing_user:
        u = existing_user
    else:
        u = User(user_key="learner")
        session.add(u)
        session.commit()
        session.refresh(u)

    start = datetime(2026, 8, 30)
    session.add(
        PredictionRecord(
            prediction_id=pid,
            user_id=u.id,
            domain="career",
            event_type="career.unexpected_task",
            description="测试预测",
            probability=probability,
            null_probability=null_prob,
            window_start=start,
            window_end=start + timedelta(hours=23, minutes=59),
            verification_due_at=start + timedelta(hours=23, minutes=59),
            success_criteria=["A"],
            failure_criteria=["B"],
            grading_rule="二值",
            status=PredictionStatus.VERIFIED.value,
        )
    )
    session.add(
        SignalRecord(
            signal_id=f"S-{pid}",
            prediction_id=pid,
            source_type="bazi",
            source_engine="bazi-0.1.0",
            domain="career",
            target_event="career.unexpected_task",
            direction=1.0, strength=0.8, confidence=0.8,
            time_scale="day",
            window_start=start, window_end=start + timedelta(days=1),
            dependency_group="lunar_calendar",
            rule_ids=[rule],
        )
    )
    session.add(
        PredictionScore(
            prediction_id=pid,
            user_id=u.id,
            probability=probability,
            outcome=outcome,
            brier=(probability - outcome) ** 2,
            log_loss=0.5,
            null_probability=null_prob,
            null_brier=(null_prob - outcome) ** 2,
            domain="career",
            time_scale="day",
        )
    )
    session.commit()
    return pid


# ------------------------------------------------------------------
def test_deterministic_attribution_overconfidence():
    """第 23 节：高概率未发生 → 过度自信假设。"""
    from app.services.learning import deterministic_attribution

    hs = deterministic_attribution(
        probability=0.9, outcome=0.0, null_probability=0.5, signals=[]
    )
    categories = {h["category"] for h in hs}
    assert "overconfidence" in categories


def test_deterministic_attribution_correlated():
    """第 20.12 / 23 节：同依赖组多信号 → 相关证据假设。"""
    from datetime import datetime

    from app.services.learning import deterministic_attribution

    from app.models.prediction import SignalRecord

    start = datetime(2026, 8, 30)
    sigs = [
        SignalRecord(signal_id=f"S{i}", prediction_id="P-X", source_type=s,
                     source_engine="x", domain="career", target_event="career.unexpected_task",
                     direction=1.0, strength=0.8, confidence=0.8, time_scale="day",
                     window_start=start, window_end=start + timedelta(days=1),
                     dependency_group="lunar_calendar")
        for i, s in enumerate(["ziwei", "bazi", "qimen"])
    ]
    hs = deterministic_attribution(
        probability=0.8, outcome=0.0, null_probability=0.5, signals=sigs
    )
    categories = {h["category"] for h in hs}
    assert "correlated_evidence" in categories


def test_run_learning_after_verify(session):
    """完整闭环：假设落库 + 规则统计 + Shadow 样本。"""
    from app.services.learning import run_learning_after_verify

    pid = _seed(session, probability=0.9, outcome=0.0)
    result = run_learning_after_verify(session, prediction_id=pid, user_id=1)
    assert result["status"] == "learned"
    assert result["hypotheses"] >= 1

    # 幂等：第二次跳过
    result2 = run_learning_after_verify(session, prediction_id=pid, user_id=1)
    assert result2["status"] == "skipped"

    # 规则统计（第 25 节）
    metric = session.exec(
        select(RuleMetric).where(RuleMetric.rule_id == "BAZI-R-test")
    ).first()
    assert metric is not None
    assert metric.call_count == 1


def test_ablation_insufficient_sample(session):
    """第 33 / 78 节：样本不足时不给结论。"""
    from app.services.ablation import run_ablation

    result = run_ablation(session, user_id=1)
    assert result["status"] == "insufficient_sample"


def test_ablation_with_samples(session):
    """第 33 节：有样本时产出各变体 Brier。"""
    from app.services.ablation import run_ablation

    for i in range(5):
        _seed(session, probability=0.6 + i * 0.05, outcome=1.0 if i % 2 else 0.0,
              rule=f"BAZI-R-{i}", pid=f"P-LEARN-{i}")

    result = run_ablation(session, user_id=1)
    assert result["status"] == "ok"
    variants = {r["variant"] for r in result["results"]}
    assert "full" in variants
    assert "null_only" in variants
    # 注意：若全部样本都含某术式，摘除后无样本，该变体会被跳过（第 78 节）——
    # 这是正确行为，不强制断言存在。
