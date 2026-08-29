"""双盲实验测试 —— 第 34 节。"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import app.core  # noqa: F401
import app.models  # noqa: F401
from app.models.core import BirthProfile, User
from app.services.pipeline import DailyPipeline


@pytest.fixture()
def session():
    e = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(e)
    with Session(e) as s:
        u = User(user_key="blind")
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
        s.commit()
        yield s


def _collect(session, arm: str | None):
    from app.core.base import AdapterQuery
    from app.schemas.signal import Domain, TimeScale, TimeWindow

    pipe = DailyPipeline(session, user_id=1)
    pipe.experiment_arm = arm

    start = datetime(2026, 9, 1)
    query = AdapterQuery(
        user_id=1,
        domain=Domain.CAREER,
        target_event="career.unexpected_task",
        time_scale=TimeScale.DAY,
        window=TimeWindow(start=start, end=start + timedelta(hours=1)),
        target_date=date(2026, 9, 1),
        target_time="14:30",
        session=session,
    )
    from app.reality.state import build_reality_state

    state = build_reality_state(session, user_id=1, target_date=date(2026, 9, 1))
    signals, null_p = pipe._collect_signals(
        event_type="career.unexpected_task",
        domain=Domain.CAREER,
        window=query.window,
        time_scale=TimeScale.DAY,
        target_date=date(2026, 9, 1),
        reality_state=state,
        experiment_arm=arm,
    )
    sources = {s.source.value for s in signals if not s.degraded}
    return sources, null_p


def test_arm_a_reality_null_excludes_metaphysical(session):
    """第 34 节 A 组：Reality + Null，无术式。"""
    sources, _ = _collect(session, "reality_null")
    metaphysical = {"ziwei", "bazi", "qimen", "liuyao", "meihua", "palm", "face"}
    assert metaphysical.isdisjoint(sources), f"A 组不应含术式信号：{sources}"


def test_arm_b_metaphysical_only_has_no_reality(session):
    """第 34 节 B 组：术式 + Null，无 Reality。"""
    sources, _ = _collect(session, "metaphysical_only")
    assert "reality" not in sources, f"B 组不应含 Reality 信号：{sources}"
    assert "null" in sources, "B 组必须保留 Null 基线"


def test_arm_c_fusion_includes_all(session):
    """第 34 节 C 组：全部信号。"""
    sources, _ = _collect(session, None)
    assert "null" in sources
    # 至少一个术式或 reality
    assert len(sources) >= 2, f"C 组信号过少：{sources}"


def test_pipeline_runs_with_arm(session):
    """三组都能跑通完整管线。"""
    for arm in ("reality_null", "metaphysical_only", None):
        pipe = DailyPipeline(session, user_id=1)
        pipe.experiment_arm = arm
        result = pipe.run(target_date=date(2026, 9, 1), scale="day", limit=4)
        assert result.scanned > 0, f"arm={arm} 扫描失败"
