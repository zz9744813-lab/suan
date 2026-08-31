"""Reality Engine 表：reality_events / daily_states。

对应工程方案第 10 / 10.1 节。

这是整个系统区别于普通算命产品的关键：系统不只靠术数，还建模用户的真实状态。
"""

from __future__ import annotations

from datetime import date, datetime

from app.utils import utcnow
from typing import Any, Optional

from sqlalchemy import JSON
from sqlmodel import Field, SQLModel


class RealityEvent(SQLModel, table=True):
    """第 61 节 Reality Event Ledger。

    验证不仅为 Prediction 服务，也沉淀为 Reality Model 的训练数据。
    """

    __tablename__ = "reality_events"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)

    occurred_on: date = Field(index=True)
    domain: str = Field(index=True, description="career / money / study / social / ...")
    event_type: str = Field(index=True, description="Event Ontology，如 career.unexpected_task")

    duration_minutes: Optional[int] = None
    magnitude: Optional[float] = Field(default=None, ge=0.0)

    # 第 55 节数据来源分层
    source: str = Field(default="USER_REPORTED_REALITY")
    confidence: float = Field(default=0.95, ge=0.0, le=1.0)

    note: str = ""
    raw: dict[str, Any] = Field(default_factory=dict, sa_type=JSON)

    # 关联到产出该事件的预测（可为空：现实事件不必来自预测）
    prediction_id: Optional[str] = Field(default=None, index=True)

    recorded_at: datetime = Field(default_factory=utcnow)


class DailyState(SQLModel, table=True):
    """第 10.1 节 RealityState 日快照。

    {
      "date": "2026-08-29",
      "career": {"job_search_activity": 0.30, "skill_learning": 0.65, "career_change_intent": 0.44},
      "study": {"last_7d_active_days": 3},
      "projects": {"active_count": 4}
    }
    """

    __tablename__ = "daily_states"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    state_date: date = Field(index=True)

    state: dict[str, Any] = Field(default_factory=dict, sa_type=JSON)

    # 派生指标（便于 SQL 聚合与 Null Model 取用）
    active_projects: Optional[int] = None
    study_minutes: Optional[int] = None
    event_count: Optional[int] = None

    computed_at: datetime = Field(default_factory=utcnow)


class UserPlan(SQLModel, table=True):
    """用户计划 / 日程。第 10 节：计划与日程是 Reality 的重要输入。

    第 20.8 节 OutcomeLeakAttack：若结果在预测前已由日历确定，则该预测判为 LEAKED。
    """

    __tablename__ = "user_plans"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)

    title: str
    planned_for: date = Field(index=True)
    planned_start: Optional[datetime] = None
    planned_end: Optional[datetime] = None

    domain: Optional[str] = None
    status: str = Field(default="planned", description="planned / done / cancelled")
    note: str = ""

    recorded_at: datetime = Field(default_factory=utcnow)
