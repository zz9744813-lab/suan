"""Null Model —— 完全不知道任何术数的基线预测模型。

对应工程方案：
- 第 11 节 Null Model
- 第 78 节 小样本保护
- 第 19.5 节 Skill Score
- 第 20.10 节 BaselineAttack

第 11 节原文：

    整个项目必须有一个：完全不知道任何术数的预测模型。

    Null Model 只允许使用：
        历史事件频率 / 星期 / 工作日 / 已知日程 / 用户计划 /
        近期行为 / 时间序列 / 简单统计

    只有传统模型长期稳定超过 Null Model，才能说明：
        Traditional Signals 提供了额外信息。

第 78 节：不能 3 次预测 3 次成功就宣布 100% 准确。
    需要最小样本量 / 贝叶斯先验 / 可信区间 / 收缩估计。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from sqlmodel import Session, func, select

from app.config import Settings, get_settings
from app.models.reality import RealityEvent
from app.schemas.signal import Signal, SourceType


@dataclass
class BaseRateEstimate:
    """带小样本保护的基础率估计（第 78 节）。"""

    probability: float
    raw_rate: float
    sample_size: int
    reliability: str  # low / medium / high
    note: str = ""


class NullModel:
    """基线模型。禁止引入任何术数信号（第 11 节）。"""

    def __init__(self, session: Session, settings: Settings | None = None) -> None:
        self.session = session
        self.settings = settings or get_settings()

    # ------------------------------------------------------------------
    def base_rate(
        self,
        *,
        user_id: int,
        event_type: str,
        as_of: date | None = None,
        lookback_days: int = 180,
        weekday: int | None = None,
    ) -> BaseRateEstimate:
        """历史事件频率 + 贝叶斯收缩（第 78 节）。

        p = (k + α·prior) / (n + α)
            k  = 回看期内事件发生的天数
            n  = 回看期总天数
            α  = PRIOR_STRENGTH（先验强度，越大越保守）

        禁止在样本不足时给出极端概率。
        """
        as_of = as_of or date.today()
        start = as_of - timedelta(days=lookback_days)

        # --- k：事件出现的「天数」（同一天多次只算一次，避免重复计数）---
        stmt = (
            select(func.count(func.distinct(RealityEvent.occurred_on)))
            .where(RealityEvent.user_id == user_id)
            .where(RealityEvent.event_type == event_type)
            .where(RealityEvent.occurred_on >= start)
            .where(RealityEvent.occurred_on <= as_of)
        )
        k = int(self.session.exec(stmt).one() or 0)

        # --- n：口径天数（可按星期过滤）---
        n = self._eligible_days(start, as_of, weekday=weekday)

        alpha = float(self.settings.PRIOR_STRENGTH)
        prior = self._global_prior(user_id, event_type) if n > 0 else 0.5

        raw_rate = (k / n) if n > 0 else 0.0
        probability = (k + alpha * prior) / (n + alpha) if (n + alpha) > 0 else prior

        return BaseRateEstimate(
            probability=round(float(probability), 4),
            raw_rate=round(raw_rate, 4),
            sample_size=n,
            reliability=self._reliability(n),
            note=(
                f"回看 {lookback_days} 天：命中 {k}/{n} 天"
                f"（原始 {raw_rate:.1%} → 收缩后 {probability:.1%}，先验 {prior:.2f}）"
            ),
        )

    # ------------------------------------------------------------------
    def signal(
        self,
        *,
        user_id: int,
        event_type: str,
        domain,
        window,
        time_scale,
        as_of: date | None = None,
    ) -> Signal:
        """Null Model 的 Signal 形式，供 Fusion 与 Skill Score 使用。

        direction 固定为 0（Null Model 不表达「倾向」，只表达「基线概率」），
        strength 用 base_rate 映射到 0~1，confidence 随样本量增长。
        """
        est = self.base_rate(
            user_id=user_id,
            event_type=event_type,
            as_of=as_of,
            weekday=window.start.weekday() if window else None,
        )

        # confidence 随样本量增长，但上限受限（第 78 节：小样本不得高置信）
        confidence = min(0.9, est.sample_size / 200.0 + 0.2)

        return Signal(
            source=SourceType.NULL,
            domain=domain,
            target_event=event_type,
            direction=0.0,          # Null 无倾向，只给基线
            strength=est.probability,
            confidence=round(confidence, 3),
            time_window=window,
            time_scale=time_scale,
            engine_version="null-0.1.0",
        )

    # ------------------------------------------------------------------
    def _eligible_days(
        self, start: date, end: date, weekday: int | None = None
    ) -> int:
        """口径内的天数。weekday 用于对「星期效应」建模（第 11 节允许）。"""
        total = 0
        cur = start
        while cur <= end:
            if weekday is None or cur.weekday() == weekday:
                total += 1
            cur += timedelta(days=1)
        return total

    def _global_prior(self, user_id: int, event_type: str) -> float:
        """先验：该用户在所有事件类型上的平均发生率。

        无数据时回落到 0.5（最大熵，不偏向任何结论）。
        """
        stmt = (
            select(func.count(func.distinct(RealityEvent.occurred_on)))
            .where(RealityEvent.user_id == user_id)
        )
        total_event_days = int(self.session.exec(stmt).one() or 0)

        first = self.session.exec(
            select(func.min(RealityEvent.occurred_on)).where(
                RealityEvent.user_id == user_id
            )
        ).one()

        if not total_event_days or first is None:
            return 0.5

        span = max(1, (date.today() - first).days + 1)
        return min(1.0, total_event_days / span * 3.0)

    @staticmethod
    def _reliability(n: int) -> str:
        """第 78 节：样本量决定可靠度标注。"""
        if n < 20:
            return "low"
        if n < 100:
            return "medium"
        return "high"
