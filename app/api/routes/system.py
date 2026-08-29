"""系统路由：用户档案 / 引擎状态 / 规则 / 本体 / 对抗性测试 / 实验。

对应工程方案：
- 第 6 节 Metaphysical Engine
- 第 25 节 Rule Registry
- 第 34 节 双盲实验模式
- 第 56 节 Event Ontology
- 第 64 节 隐私
- 第 65 节 关键安全边界
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app.core.base import registry as adapter_registry
from app.database import get_session
from app.models.core import BirthProfile, User
from app.models.registry import Rule
from app.prediction.ontology import ONTOLOGY, all_event_types

router = APIRouter()


# ======================================================================
# 引擎状态
# ======================================================================
@router.get("/system/engines")
def engines():
    """七个术式 Adapter 的可用性。不可用时返回 degraded 原因。"""
    return {
        "engines": [
            {
                "source": a.source.value,
                "engine": a.engine_name,
                "version": a.engine_version,
                "available": a.available,
            }
            for a in adapter_registry.all()
        ],
        "available_count": len(adapter_registry.available_sources()),
    }


# ======================================================================
# 用户与出生档案
# ======================================================================
class BirthProfileIn(BaseModel):
    solar_birth_date: date
    solar_birth_time: str = "00:00"
    birth_time_known: bool = False
    gender: str = "unknown"
    birth_place: str = ""
    longitude: float | None = None
    latitude: float | None = None
    use_true_solar_time: bool = True


class UserIn(BaseModel):
    user_key: str
    display_name: str = ""
    timezone: str = "Asia/Shanghai"
    birth_profile: BirthProfileIn | None = None


@router.post("/users")
def create_user(payload: UserIn, session: Session = Depends(get_session)):
    existing = session.exec(select(User).where(User.user_key == payload.user_key)).first()
    if existing:
        raise HTTPException(409, f"用户已存在：{payload.user_key}")

    user = User(
        user_key=payload.user_key,
        display_name=payload.display_name,
        timezone=payload.timezone,
    )
    session.add(user)
    session.commit()
    session.refresh(user)

    if payload.birth_profile:
        bp = payload.birth_profile
        session.add(
            BirthProfile(
                user_id=user.id,  # type: ignore[arg-type]
                solar_birth_date=bp.solar_birth_date,
                solar_birth_time=bp.solar_birth_time,
                birth_time_known=bp.birth_time_known,
                gender=bp.gender,
                birth_place=bp.birth_place,
                longitude=bp.longitude,
                latitude=bp.latitude,
                use_true_solar_time=bp.use_true_solar_time,
            )
        )
        session.commit()

    return {"user_id": user.id, "user_key": user.user_key}


@router.get("/users")
def list_users(session: Session = Depends(get_session)):
    rows = session.exec(select(User)).all()
    return {"count": len(rows), "items": [{"id": u.id, "user_key": u.user_key} for u in rows]}


@router.get("/users/{user_id}/profile")
def get_profile(user_id: int, session: Session = Depends(get_session)):
    """出生档案属高敏感个人数据（第 64 节）。骨架阶段不做鉴权，部署前必须加。"""
    profile = session.exec(
        select(BirthProfile).where(BirthProfile.user_id == user_id)
    ).first()
    if profile is None:
        raise HTTPException(404, "未找到出生档案")
    return profile


# ======================================================================
# Event Ontology（第 56 节）
# ======================================================================
@router.get("/ontology")
def ontology(domain: str | None = None, scale: str | None = None):
    items = [
        {
            "event_type": s.event_type,
            "domain": s.domain,
            "label": s.label,
            "success_criteria": list(s.success_criteria),
            "failure_criteria": list(s.failure_criteria),
            "preferred_scales": list(s.preferred_scales),
        }
        for s in ONTOLOGY.values()
        if (domain is None or s.domain == domain)
        and (scale is None or scale in s.preferred_scales)
    ]
    return {"count": len(items), "items": items, "all_types": all_event_types()}


# ======================================================================
# Rule Registry（第 25 节）
# ======================================================================
@router.get("/rules")
def list_rules(
    school: str | None = None,
    status: str | None = "active",
    session: Session = Depends(get_session),
):
    stmt = select(Rule)
    if school:
        stmt = stmt.where(Rule.school == school)
    if status:
        stmt = stmt.where(Rule.status == status)
    rows = session.exec(stmt).all()
    return {
        "count": len(rows),
        "items": [
            {
                "rule_id": r.rule_id,
                "school": r.school,
                "description": r.description,
                "domains": r.domains,
                "supported_windows": r.supported_windows,
                "version": r.version,
                "status": r.status,
            }
            for r in rows
        ],
    }


# ======================================================================
# 对抗性 Gate 手动测试（第 20 / 21 节）
# ======================================================================
class GateTestIn(BaseModel):
    description: str = ""
    event_type: str = ""
    probability: float | None = None
    null_probability: float | None = None
    success_criteria: list[str] = Field(default_factory=list)
    failure_criteria: list[str] = Field(default_factory=list)
    window_start: datetime | None = None
    window_end: datetime | None = None
    signals: list[dict[str, Any]] = Field(default_factory=list)
    agent_texts: dict[str, str] = Field(default_factory=dict)


@router.post("/adversarial/gate-test")
def gate_test(payload: GateTestIn):
    """手动跑一遍 14 种攻击，用于调试与教学。

    这是核心基础设施，不是附属 Agent（第 20 节）。
    """
    from app.adversarial.attacks.base import AttackContext
    from app.adversarial.gate import AdversarialGate

    groups: dict[str, list[str]] = {}
    for s in payload.signals:
        key = s.get("dependency_group") or f"solo:{s.get('source', 'unknown')}"
        groups.setdefault(key, []).append(str(s.get("source", "unknown")))

    ctx = AttackContext(
        description=payload.description,
        event_type=payload.event_type,
        probability=payload.probability,
        null_probability=payload.null_probability,
        success_criteria=payload.success_criteria,
        failure_criteria=payload.failure_criteria,
        window_start=payload.window_start,
        window_end=payload.window_end,
        signals=payload.signals,
        dependency_groups=groups,
        agent_texts=payload.agent_texts,
    )

    result = AdversarialGate().run(ctx)
    return {
        "decision": result.decision,
        "attacks": [
            {
                "attack": o.attack,
                "verdict": o.verdict.value,
                "severity": o.severity,
                "reason": o.reason,
                "details": o.details,
            }
            for o in result.outcomes
        ],
    }


# ======================================================================
# 日历快照（第 6 节 Calendar Core）
# ======================================================================
@router.get("/calendar/snapshot")
def calendar_snapshot(
    user_id: int = Query(...),
    target_date: date | None = None,
    session: Session = Depends(get_session),
):
    """第 6 节：所有术式共享同一个 Calendar Core。"""
    from app.core.calendar.core import CalendarCore

    profile = session.exec(
        select(BirthProfile).where(BirthProfile.user_id == user_id)
    ).first()
    if profile is None:
        raise HTTPException(404, "未找到出生档案，无法计算历法快照")

    target_date = target_date or date.today()
    core = CalendarCore()
    result = core.compute(
        birth_date=profile.solar_birth_date,
        birth_time=profile.solar_birth_time,
        target_date=target_date,
        gender=profile.gender,
        use_true_solar_time=profile.use_true_solar_time,
        longitude=profile.longitude,
    )
    return {
        "target_date": target_date.isoformat(),
        "degraded": result.degraded,
        "degrade_reason": result.degrade_reason,
        "payload": result.payload,
    }
