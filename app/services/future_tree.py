"""Future Tree —— 人生情景树。

对应工程方案第 27 节：

    系统除了单事件预测，还建立人生情景树。
        Current State
             ├── Scenario A 46%  ← 当前轨迹继续
             ├── Scenario B 34%  ← 职业发生重要变化
             └── Scenario C 20%  ← 新项目成为主要重心

    Future Tree 不是一次生成后永久固定。
    每周重新计算：P(Scenario | New Evidence)

实现：
    确定性生成（基于 RealityState 历史趋势 + RealityEvent 领域频率），
    可叠加 LLM 增强。第 54 节原则：同输入同输出。
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

from sqlmodel import Session, select

from app.models.reality import DailyState, RealityEvent


@dataclass
class Scenario:
    key: str
    label: str
    probability: float
    description: str
    evidence: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "probability": round(self.probability, 4),
            "description": self.description,
            "evidence": self.evidence,
        }


class FutureTreeBuilder:
    """基于现实数据构建情景树。"""

    def __init__(self, session: Session, user_id: int) -> None:
        self.session = session
        self.user_id = user_id

    # ------------------------------------------------------------------
    def build(self, as_of: date | None = None, horizon_days: int = 365) -> dict[str, Any]:
        """构建情景树。as_of 为基准日（用于每周重算）。

        第 27 节：每周按新证据重算 P(Scenario | New Evidence)。
        同 as_of 同数据 → 同结果（确定性）。
        """
        as_of = as_of or date.today()

        states = self._recent_states(as_of, days=30)
        events = self._recent_events(as_of, days=90)

        # ---------- 指标 ----------
        study_trend = _trend([s.study_minutes or 0 for s in states])
        project_count = states[-1].active_projects if states else 0
        event_activity = sum(s.event_count or 0 for s in states) / max(1, len(states))

        domain_freq = _domain_frequencies(events)
        career_activity = domain_freq.get("career", 0.0)
        project_activity = domain_freq.get("project", 0.0)

        # ---------- 三个情景（第 27 节结构）----------
        # Scenario A：当前轨迹继续
        p_a = 0.5 + 0.2 * (1.0 - abs(study_trend)) + 0.05 * min(1.0, project_count)
        # Scenario B：职业重要变化（career 活跃度高 + 学习趋势转向时上升）
        p_b = 0.2 + 0.3 * career_activity + 0.1 * max(0.0, -study_trend)
        # Scenario C：新项目成为主要重心
        p_c = 0.15 + 0.25 * project_activity + 0.1 * max(0.0, study_trend)

        total = p_a + p_b + p_c
        scenarios = [
            Scenario(
                key="A",
                label="当前轨迹继续",
                probability=p_a / total,
                description=f"保持现状推进：学习{'上升' if study_trend > 0.02 else '平稳' if study_trend > -0.02 else '下降'}，"
                            f"活跃项目 {project_count} 个，日均事件 {event_activity:.1f} 次",
                evidence=[f"近30天学习趋势 {study_trend:+.2f}", f"活跃项目 {project_count}"],
            ),
            Scenario(
                key="B",
                label="职业发生重要变化",
                probability=p_b / total,
                description=f"职业领域事件占比 {career_activity:.0%}，"
                            f"{'学习趋势转向' if study_trend < 0 else '职业活动活跃'}，"
                            f"可能出现岗位/方向调整",
                evidence=[f"career 事件占比 {career_activity:.0%}"],
            ),
            Scenario(
                key="C",
                label="新项目成为主要重心",
                probability=p_c / total,
                description=f"项目领域事件占比 {project_activity:.0%}，"
                            f"{'学习势头上升' if study_trend > 0 else '项目推进活跃'}，"
                            f"新项目可能挤占既有安排",
                evidence=[f"project 事件占比 {project_activity:.0%}"],
            ),
        ]

        # 归一化并排序
        scenarios.sort(key=lambda s: s.probability, reverse=True)

        return {
            "as_of": as_of.isoformat(),
            "horizon_days": horizon_days,
            "scenarios": [s.to_dict() for s in scenarios],
            "input_hash": self._input_hash(as_of, study_trend, career_activity, project_activity),
            "note": "基于现实数据的确定性外推，每周按新证据重算（第 27 节）",
        }

    # ------------------------------------------------------------------
    def _recent_states(self, as_of: date, days: int) -> list[DailyState]:
        start = as_of - timedelta(days=days)
        return list(
            self.session.exec(
                select(DailyState)
                .where(DailyState.user_id == self.user_id)
                .where(DailyState.state_date >= start)
                .where(DailyState.state_date <= as_of)
                .order_by(DailyState.state_date)
            ).all()
        )

    def _recent_events(self, as_of: date, days: int) -> list[RealityEvent]:
        start = as_of - timedelta(days=days)
        return list(
            self.session.exec(
                select(RealityEvent)
                .where(RealityEvent.user_id == self.user_id)
                .where(RealityEvent.occurred_on >= start)
                .where(RealityEvent.occurred_on <= as_of)
            ).all()
        )

    @staticmethod
    def _input_hash(as_of: date, trend: float, career: float, project: float) -> str:
        raw = f"ft:{as_of}:{trend:.4f}:{career:.4f}:{project:.4f}"
        return hashlib.sha256(raw.encode()).hexdigest()


def _domain_frequencies(events: list[RealityEvent]) -> dict[str, float]:
    """各领域事件占比。"""
    total = len(events)
    if total == 0:
        return {}
    freq: dict[str, int] = {}
    for ev in events:
        freq[ev.domain] = freq.get(ev.domain, 0) + 1
    return {k: v / total for k, v in freq.items()}


def _trend(values: list[float]) -> float:
    """简单线性趋势：归一化斜率。"""
    if len(values) < 3:
        return 0.0
    n = len(values)
    xs = list(range(n))
    mean_x = sum(xs) / n
    mean_y = sum(values) / n
    denom = sum((x - mean_x) ** 2 for x in xs)
    if denom == 0:
        return 0.0
    slope = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, values)) / denom
    # 归一化到 [-1, 1]
    return max(-1.0, min(1.0, slope / (max(1e-6, mean_y or 1.0))))
