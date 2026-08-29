"""RealityState —— 现实状态与行为模型。

对应工程方案第 10 / 10.1 节：

    这是整个系统区别于普通算命产品的关键。

    现实模型记录：计划 / 日程 / 目标 / 日记 / 任务 / 学习 / 项目 /
                  职业行为 / 消费事件 / 沟通事件 / 重大生活事件 / 用户主动输入

第 10.1 节输出结构：
    {
      "date": "2026-08-29",
      "career": {"job_search_activity": 0.30, "skill_learning": 0.65, ...},
      "study":  {"last_7d_active_days": 3},
      "projects": {"active_count": 4}
    }
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from sqlmodel import Session, func, select

from app.models.reality import DailyState, RealityEvent, UserPlan

# domain → 该领域在 RealityState 中的强度指标名
DOMAIN_INTENSITY_KEY: dict[str, str] = {
    "career": "activity",
    "money": "spend_intent",
    "study": "learning_intensity",
    "social": "social_intensity",
    "project": "progress_rate",
    "communication": "message_volume",
    "habit": "consistency",
    "schedule": "load",
}


def build_reality_state(
    session: Session,
    *,
    user_id: int,
    target_date: date | None = None,
    lookback_days: int = 7,
) -> dict[str, Any]:
    """构建某日的 RealityState。纯统计，不含任何术数（第 10 节）。"""
    target_date = target_date or date.today()
    start = target_date - timedelta(days=lookback_days - 1)

    events = session.exec(
        select(RealityEvent)
        .where(RealityEvent.user_id == user_id)
        .where(RealityEvent.occurred_on >= start)
        .where(RealityEvent.occurred_on <= target_date)
    ).all()

    # ---------- 按 domain 聚合 ----------
    by_domain: dict[str, dict[str, Any]] = {}
    for ev in events:
        d = by_domain.setdefault(ev.domain, {})
        d["count"] = d.get("count", 0) + 1
        d["minutes"] = d.get("minutes", 0) + (ev.duration_minutes or 0)
        d["active_days"] = len({e.occurred_on for e in events if e.domain == ev.domain})

    state: dict[str, Any] = {"date": target_date.isoformat()}

    for domain, agg in by_domain.items():
        # 强度：活跃天数占比（0~1）
        intensity = min(1.0, agg["active_days"] / max(1, lookback_days))
        key = DOMAIN_INTENSITY_KEY.get(domain, "activity")
        state[domain] = {
            key: round(intensity, 3),
            "event_count": agg["count"],
            "total_minutes": agg["minutes"],
            "active_days": agg["active_days"],
            f"last_{lookback_days}d_active_days": agg["active_days"],
        }

    # ---------- 当日计划负载 ----------
    plans = session.exec(
        select(UserPlan)
        .where(UserPlan.user_id == user_id)
        .where(UserPlan.planned_for == target_date)
    ).all()
    state["schedule"] = {
        **(state.get("schedule", {})),
        "planned_items": len(plans),
        "planned_done": sum(1 for p in plans if p.status == "done"),
        "planned_cancelled": sum(1 for p in plans if p.status == "cancelled"),
    }

    # ---------- 全局活跃度 ----------
    total_active_days = len({e.occurred_on for e in events})
    state["_meta"] = {
        "lookback_days": lookback_days,
        "total_events": len(events),
        "active_days": total_active_days,
        "activity_ratio": round(total_active_days / max(1, lookback_days), 3),
    }

    return state


def persist_daily_state(
    session: Session, *, user_id: int, target_date: date | None = None
) -> DailyState:
    """计算并落库 DailyState（幂等：同 user+date 覆盖更新）。"""
    target_date = target_date or date.today()
    state = build_reality_state(session, user_id=user_id, target_date=target_date)

    existing = session.exec(
        select(DailyState)
        .where(DailyState.user_id == user_id)
        .where(DailyState.state_date == target_date)
    ).first()

    meta = state.get("_meta", {})
    if existing:
        existing.state = state
        existing.active_projects = int(state.get("project", {}).get("active_days", 0))
        existing.study_minutes = int(state.get("study", {}).get("total_minutes", 0))
        existing.event_count = int(meta.get("total_events", 0))
        existing.computed_at = func.now()  # type: ignore[assignment]
        session.add(existing)
        session.commit()
        session.refresh(existing)
        return existing

    row = DailyState(
        user_id=user_id,
        state_date=target_date,
        state=state,
        active_projects=int(state.get("project", {}).get("active_days", 0)),
        study_minutes=int(state.get("study", {}).get("total_minutes", 0)),
        event_count=int(meta.get("total_events", 0)),
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row
