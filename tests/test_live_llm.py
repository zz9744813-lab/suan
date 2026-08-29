"""真实 LLM 冒烟测试（默认跳过，手动运行）。

qiyovo 中转站对长请求慢（实测 ~50s/次），因此：
- 默认跳过（XUANMIRROR_LIVE_LLM=1 时启用）
- 只验证关键路径：Agent 能调用 LLM 并输出结构化 JSON

运行：XUANMIRROR_LIVE_LLM=1 pytest tests/test_live_llm.py -v
"""

from __future__ import annotations

import datetime
import os

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import app.core  # noqa: F401
import app.models  # noqa: F401
from app.agents.base import AgentContext
from app.agents.signal_agents import BaziAgent
from app.models.core import BirthProfile, User

pytestmark = pytest.mark.skipif(
    os.getenv("XUANMIRROR_LIVE_LLM") != "1",
    reason="需要真实 LLM 网络（XUANMIRROR_LIVE_LLM=1 启用）",
)


@pytest.fixture()
def ctx():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        u = User(user_key="live")
        s.add(u)
        s.commit()
        s.refresh(u)
        s.add(
            BirthProfile(
                user_id=u.id,
                solar_birth_date=datetime.date(1990, 5, 15),
                solar_birth_time="14:30",
                birth_time_known=True,
                gender="male",
            )
        )
        s.commit()

        from app.core.calendar.core import CalendarCore

        r = CalendarCore().compute(
            birth_date=datetime.date(1990, 5, 15), birth_time="14:30",
            target_date=datetime.date(2026, 9, 1), gender="male",
        )
        yield AgentContext(
            user_id=u.id,
            session=s,
            target_event="career.unexpected_task",
            domain="career",
            payload={"chart": r.payload, "time_scale": "day"},
        )


def test_bazi_agent_live_llm(ctx):
    """第 43 节：Agent 必须输出结构化 JSON（abstain 或 direction 字段）。"""
    res = BaziAgent().run(ctx)
    assert res.ok, f"LLM 调用失败：{res.error}"
    assert isinstance(res.output, dict)
    assert "abstain" in res.output or "direction" in res.output
    # Agent 落库了 agent_runs（第 40 节可重放）
    assert res.run_id.startswith("RUN-")


def test_agent_runs_recorded(ctx):
    """第 40 节：每一次 LLM 调用必须可重放。"""
    from app.models.registry import AgentRun

    res = BaziAgent().run(ctx)
    row = ctx.session.get(AgentRun, 1) if ctx.session else None
    # 通过 run_id 查询
    from sqlmodel import select

    row = ctx.session.exec(
        select(AgentRun).where(AgentRun.run_id == res.run_id)
    ).first() if ctx.session else None
    assert row is not None
    assert row.agent == "BaziAgent"
    assert row.output_json  # 结构化输出已落库
