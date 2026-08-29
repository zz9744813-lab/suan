"""Counterfactual Engine —— 反事实推演。

对应工程方案第 28 节：

    允许用户问：
        「如果我什么都不改变，一年后怎样？」
        「如果每天做 X，每周做 Y，停止 Z，一年后怎样？」

    比较：
        Baseline Scenario
        Intervention Scenario A
        Intervention Scenario B

    这部分重点不是术数，而是 Decision Intelligence。

实现：
    确定性外推模型（基于 RealityState 趋势 + 干预的假设效应），
    可叠加 LLM 增强。干预效应参数化，用户可调。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from sqlmodel import Session, select

from app.models.reality import DailyState

# 领域 → 一年后的估算维度
DIMENSIONS = ["study", "career", "project", "social", "health"]


@dataclass
class Scenario:
    key: str
    label: str
    dimensions: dict[str, float] = field(default_factory=dict)
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "dimensions": {k: round(v, 2) for k, v in self.dimensions.items()},
            "description": self.description,
        }


class CounterfactualEngine:
    """Baseline vs Intervention 对比。"""

    def __init__(self, session: Session, user_id: int) -> None:
        self.session = session
        self.user_id = user_id

    # ------------------------------------------------------------------
    def compare(
        self,
        *,
        interventions: list[dict[str, Any]] | None = None,
        horizon_days: int = 365,
        as_of: date | None = None,
    ) -> dict[str, Any]:
        """输出 Baseline + 各干预情景。

        interventions: [{"label": "每天学习1小时", "effects": {"study": 0.3}}]
        effects 表示该干预对领域强度（0-1）的假设提升。
        """
        as_of = as_of or date.today()
        base = self._baseline_dimensions(as_of)

        scenarios = [
            Scenario(
                key="baseline",
                label="什么都不改变",
                dimensions=base,
                description="基于当前现实轨迹的线性外推（不引入任何干预）",
            )
        ]

        for i, iv in enumerate(interventions or [], start=1):
            effects: dict[str, float] = iv.get("effects") or {}
            sim = dict(base)
            desc_parts = []
            for dim, boost in effects.items():
                if dim in sim:
                    old = sim[dim]
                    # 干预效应：提升但衰减（不可能无限提升）
                    sim[dim] = min(1.0, old + boost * (1.0 - old))
                    desc_parts.append(f"{dim} 强度 {old:.2f}→{sim[dim]:.2f}")
            scenarios.append(
                Scenario(
                    key=f"intervention_{i}",
                    label=str(iv.get("label") or f"干预 {i}"),
                    dimensions=sim,
                    description="；".join(desc_parts) or "干预未作用于任何维度",
                )
            )

        return {
            "as_of": as_of.isoformat(),
            "horizon_days": horizon_days,
            "note": "确定性外推模型（Decision Intelligence，第 28 节），干预效应为假设参数",
            "scenarios": [s.to_dict() for s in scenarios],
        }

    # ------------------------------------------------------------------
    def _baseline_dimensions(self, as_of: date) -> dict[str, float]:
        """当前状态 → 一年后基线（趋势外推 + 均值回归）。"""
        states = list(
            self.session.exec(
                select(DailyState)
                .where(DailyState.user_id == self.user_id)
                .where(DailyState.state_date >= as_of - timedelta(days=30))
                .order_by(DailyState.state_date)
            ).all()
        )

        if not states:
            # 无数据：中性基线
            return {d: 0.3 for d in DIMENSIONS}

        # 学习强度：日均学习分钟 → 0-1
        study_minutes = sum(s.study_minutes or 0 for s in states) / len(states)
        study = min(1.0, study_minutes / 120.0)

        # 项目活跃度
        projects = sum(s.active_projects or 0 for s in states) / len(states)
        project = min(1.0, projects / 5.0)

        # 事件负载（社交/职业活跃度代理）
        events = sum(s.event_count or 0 for s in states) / len(states)
        social = min(1.0, events / 8.0)
        career = min(1.0, max(0.2, events / 6.0))
        health = 0.7  # 未知维度给中性偏上

        base = {
            "study": study,
            "career": career,
            "project": project,
            "social": social,
            "health": health,
        }
        # 均值回归：一年后向 0.5 收敛 20%
        return {k: v + (0.5 - v) * 0.2 for k, v in base.items()}
