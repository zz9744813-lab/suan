"""Obsidian 导出与报告测试 —— 第 62 / 63 / 30 / 31 / 32 节。"""

from __future__ import annotations

import datetime
from pathlib import Path

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import app.models  # noqa: F401
from app.models.core import User
from app.models.prediction import PredictionRecord
from app.models.reality import RealityEvent
from app.schemas.prediction import PredictionStatus


@pytest.fixture()
def session():
    e = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(e)
    with Session(e) as s:
        u = User(user_key="exp")
        s.add(u)
        s.commit()
        s.refresh(u)

        start = datetime.datetime(2026, 8, 30)
        s.add(
            PredictionRecord(
                prediction_id="P-EXP-1",
                user_id=u.id,
                domain="career",
                event_type="career.unexpected_task",
                description="出现临时工作任务",
                probability=0.67,
                null_probability=0.52,
                window_start=start,
                window_end=start + datetime.timedelta(hours=23, minutes=59),
                verification_due_at=start + datetime.timedelta(hours=23, minutes=59),
                success_criteria=["出现临时任务", "计划改变30分钟"],
                failure_criteria=["未出现"],
                grading_rule="二值",
                status=PredictionStatus.FROZEN.value,
                sha256="a" * 64,
            )
        )
        s.add(
            RealityEvent(
                user_id=u.id,
                occurred_on=datetime.date(2026, 8, 25),
                domain="career",
                event_type="career.unexpected_task",
                source="user_report",
            )
        )
        s.commit()
        yield s


def test_daily_forecast_markdown(session, tmp_path):
    """第 63 节：格式正确的 Markdown 日报。"""
    from app.services.exports import daily_forecast_markdown

    md = daily_forecast_markdown(
        session, user_id=1, target_date=datetime.date(2026, 8, 30)
    )
    assert "# 2026-08-30 Future Forecast" in md
    assert "career.unexpected_task" in md
    assert "成功标准" in md or "成功标准：" in md
    assert "计划改变30分钟" in md


def test_export_obsidian_vault(session, tmp_path):
    """第 62 节：生成目录结构 + 文件。"""
    from app.services.exports import export_obsidian_vault

    base = tmp_path / "XuanMirror"
    result = export_obsidian_vault(session, user_id=1, base_dir=base)

    assert result["count"] >= 3  # 仪表盘 + 本命 + 预测 + 现实事件
    assert (base / "00_仪表盘.md").exists()
    assert (base / "01_本命档案.md").exists()
    # 预测文件
    pred_files = list((base / "02_每日预测").glob("*.md"))
    assert len(pred_files) == 1
    # 现实事件
    ev_files = list((base / "04_现实事件").glob("*.md"))
    assert len(ev_files) == 1


def test_weekly_report_deterministic(session):
    """第 30 节：LLM 不可用（mock）时返回统计版。"""
    from app.services.reports import weekly_report

    md = weekly_report(session, user_id=1)
    assert isinstance(md, str)
    assert "周报" in md or "周" in md
    # 统计版包含概率质量
    assert "Brier" in md or "样本" in md


def test_monthly_report_deterministic(session):
    from app.services.reports import monthly_report

    md = monthly_report(session, user_id=1)
    assert isinstance(md, str) and len(md) > 0


def test_audit_report_ten_questions(session):
    """第 32 节：第一性原理审计必须覆盖 10 问。"""
    from app.services.reports import audit_report

    result = audit_report(session, user_id=1)
    assert result["status"] in ("ok", "deterministic")
    answers = result["answers"]
    assert len(answers) == 10
    for a in answers:
        assert "question" in a and "answer" in a
