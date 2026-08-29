"""Prediction Budget —— 禁止「撒网式算准」。

对应工程方案第 4 节。

第 4.1 节：
    如果系统每天预测 100 件事，最终发生 20 件，再只展示 20 件：
    「命中 20 项」—— 这是无效实验。

第 4.2 节 强制下注制度：
    明日强预测 5 / 明日观察预测 5 / 7 天 5 / 30 天 5 / 90 天 3
    只有最高信息价值的预测才能获得预测额度。

第 4.3 节 Information Value：
    IV = Novelty × Confidence × Falsifiability × PersonalRelevance × ModelDisagreementValue

    优先发布：
    - 系统非常有把握；
    - 多模型明显分歧；
    - 与用户现实高度相关；
    - 可清楚验证；
    - 对模型校准价值高。
"""

from __future__ import annotations

from dataclasses import dataclass

from app.config import Settings, get_settings
from app.schemas.prediction import PredictionCandidate
from app.schemas.signal import TimeScale


@dataclass
class BudgetSlot:
    """一个预算槽位。"""

    key: str
    time_scale: TimeScale
    strength: str  # strong / watch
    limit: int

    def matches(self, cand: PredictionCandidate) -> bool:
        return cand.time_scale == self.time_scale


def default_slots(settings: Settings | None = None) -> list[BudgetSlot]:
    """第 4.2 节默认额度。"""
    s = settings or get_settings()
    table = s.budget_table
    return [
        BudgetSlot("tomorrow_strong", TimeScale.DAY, "strong", table["tomorrow_strong"]),
        BudgetSlot("tomorrow_watch", TimeScale.DAY, "watch", table["tomorrow_watch"]),
        BudgetSlot("7d", TimeScale.WEEK, "strong", table["7d"]),
        BudgetSlot("30d", TimeScale.MONTH, "strong", table["30d"]),
        BudgetSlot("90d", TimeScale.YEAR, "strong", table["90d"]),
    ]


# 概率阈值：高于此值算「强预测」，否则为「观察预测」
STRONG_PROBABILITY_THRESHOLD = 0.6


def compute_disagreement(cand: PredictionCandidate) -> float:
    """第 4.3 节 ModelDisagreementValue：多模型分歧越大，验证价值越高。

    用各 Signal 的 signed_strength 极差衡量。
    """
    values = [s.signed_strength for s in cand.signals if not s.degraded]
    if len(values) < 2:
        return 0.5
    return min(1.0, (max(values) - min(values)) / 2.0)


def score_candidate(cand: PredictionCandidate) -> float:
    """综合 IV 评分。缺失的维度按中性 0.5 处理。"""
    iv = cand.information_value
    # 第 4.3 节：分歧值从信号实时算，不用配置里的静态值
    disagreement = compute_disagreement(cand)
    return iv.novelty * iv.confidence * iv.falsifiability * iv.personal_relevance * disagreement


def apply_budget(
    candidates: list[PredictionCandidate],
    slots: list[BudgetSlot] | None = None,
) -> tuple[list[PredictionCandidate], dict[str, int]]:
    """按预算竞争筛选候选。

    第 4 节：只有最高信息价值的预测才能获得预测额度。
    未获得额度的候选不进入 Prediction Ledger（第 20.6 节：
    候选命中不得算作正式命中）。

    返回：(中选候选, 各槽位使用统计)
    """
    slots = slots or default_slots()
    ranked = sorted(candidates, key=score_candidate, reverse=True)

    usage = {s.key: 0 for s in slots}
    selected: list[PredictionCandidate] = []

    for cand in ranked:
        for slot in slots:
            if not slot.matches(cand):
                continue

            # strong / watch 分流：按概率高低
            is_strong = cand.probability >= STRONG_PROBABILITY_THRESHOLD
            if slot.strength == "strong" and not is_strong:
                continue
            if slot.strength == "watch" and is_strong:
                continue

            if usage[slot.key] >= slot.limit:
                continue

            cand.budget_granted = True
            usage[slot.key] += 1
            selected.append(cand)
            break

    return selected, usage
