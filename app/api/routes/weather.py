"""天气校准健身房路由（2026-09-26 round 28）。

全部 POST 端点挂跨站写防护；preview 为只读。
车道独立于个人预测（domain=weather），共用冻结账本与评分表。
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select

from app.api.deps import enforce_same_origin
from app.database import get_session
from app.models.core import User
from app.services import weather_gym

router = APIRouter(
    prefix="/weather",
    dependencies=[Depends(enforce_same_origin)],
)


def _uid(session: Session) -> int:
    user = session.exec(select(User).where(User.is_active.is_(True))).first()
    if user is None or user.id is None:
        raise HTTPException(404, "无活跃用户——请先在设置页创建出生档案")
    return user.id


@router.get("/preview")
def preview(target: date | None = None):
    """展示指定日（默认明天）候选与 Null 基线，不落库。"""
    return weather_gym.preview_weather(target)


@router.post("/seed")
def seed(
    target: date | None = None,
    session: Session = Depends(get_session),
):
    """冻结目标日（默认明天）的天气候选（幂等：同日同事件跳过）。"""
    return weather_gym.seed_weather(session, _uid(session), target)


@router.post("/verify-due")
def verify_due(
    session: Session = Depends(get_session),
):
    """对所有到期天气预测做机械验证（零人工裁量）。"""
    return weather_gym.verify_due_weather(session, _uid(session))


@router.post("/backfill")
def backfill(
    start: date = Query(...),
    end: date = Query(...),
    stride_days: int = Query(3, ge=1, le=30),
    session: Session = Depends(get_session),
):
    """历史回填（provenance=backfill）：冻结过去候选并立即机械判定。

    回填样本只作校准种子与引擎体检，不得混入 live 技能统计（C-006）。
    """
    return weather_gym.backfill_weather(
        session, _uid(session), start, end, stride_days=stride_days
    )
