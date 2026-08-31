"""Scheduler 测试 —— 第 58 节。"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from app.utils import utcnow

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import app.models  # noqa: F401
from app.config import Settings
from app.models.core import User
from app.models.prediction import PredictionRecord
from app.schemas.prediction import PredictionStatus


@pytest.fixture()
def engine():
    e = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(e)
    return e


def test_scheduler_disabled_by_default(engine):
    """SCHEDULER_ENABLED=false 时不构建调度器（避免开发机空转烧 token）。"""
    from app.scheduler import build_scheduler

    s = build_scheduler(engine, Settings(SCHEDULER_ENABLED=False))
    assert s is None


def test_scheduler_jobs_when_enabled(engine):
    """第 58 节时间表：23:30 Reality → 23:40 管线 → 21:00 验证提醒。"""
    from app.scheduler import build_scheduler

    s = build_scheduler(engine, Settings(SCHEDULER_ENABLED=True))
    jobs = {j.id: str(j.trigger) for j in s.get_jobs()}
    assert "reality_update" in jobs and "hour='23'" in jobs["reality_update"] and "minute='30'" in jobs["reality_update"]
    assert "daily_pipeline" in jobs and "hour='23'" in jobs["daily_pipeline"] and "minute='40'" in jobs["daily_pipeline"]
    assert "verify_reminder" in jobs and "hour='21'" in jobs["verify_reminder"] and "minute='0'" in jobs["verify_reminder"]
    if s.running:
        s.shutdown(wait=False)


def test_verify_reminder_marks_due(engine):
    """第 59 节：今天到期的 FROZEN 预测 → VERIFY_REQUIRED。"""
    from app.scheduler import job_verify_reminder

    with Session(engine) as s:
        u = User(user_key="sched")
        s.add(u)
        s.commit()
        s.refresh(u)

        today = utcnow().date()
        window_start = datetime(today.year, today.month, today.day, 0, 0, 0)
        s.add(
            PredictionRecord(
                prediction_id="P-SCHED-1",
                user_id=u.id,
                domain="career",
                event_type="career.unexpected_task",
                description="测试预测",
                probability=0.6,
                window_start=window_start,
                window_end=window_start + timedelta(hours=23, minutes=59, seconds=59),
                verification_due_at=window_start + timedelta(hours=23, minutes=59),
                success_criteria=["A"],
                failure_criteria=["B"],
                grading_rule="二值",
                status=PredictionStatus.FROZEN.value,
            )
        )
        s.commit()

    job_verify_reminder(engine)

    with Session(engine) as s:
        row = s.exec(
            select(PredictionRecord).where(
                PredictionRecord.prediction_id == "P-SCHED-1"
            )
        ).first()
        assert row.status == PredictionStatus.VERIFY_REQUIRED.value


def test_verify_reminder_ignores_future(engine):
    """未到期的预测保持 FROZEN。"""
    from app.scheduler import job_verify_reminder

    with Session(engine) as s:
        u = User(user_key="sched2")
        s.add(u)
        s.commit()
        s.refresh(u)

        future = utcnow() + timedelta(days=5)
        s.add(
            PredictionRecord(
                prediction_id="P-SCHED-2",
                user_id=u.id,
                domain="career",
                event_type="career.unexpected_task",
                description="未来预测",
                probability=0.6,
                window_start=future,
                window_end=future + timedelta(hours=23, minutes=59),
                verification_due_at=future + timedelta(hours=23, minutes=59),
                success_criteria=["A"],
                failure_criteria=["B"],
                grading_rule="二值",
                status=PredictionStatus.FROZEN.value,
            )
        )
        s.commit()

    job_verify_reminder(engine)

    with Session(engine) as s:
        row = s.exec(
            select(PredictionRecord).where(
                PredictionRecord.prediction_id == "P-SCHED-2"
            )
        ).first()
        assert row.status == PredictionStatus.FROZEN.value
