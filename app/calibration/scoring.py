"""概率评分。

对应工程方案：
- 第 19.1 节 Brier Score
- 第 19.2 节 Log Loss
- 第 19.3 节 Calibration
- 第 19.4 节 Sharpness
- 第 19.5 节 Skill Score
- 第 78 节 小样本保护

禁止 4：不能用命中率一个指标，必须概率评分。

第 19.4 节：
    一个模型如果永远预测 50%，虽然可能校准不错，但毫无信息价值。
    因此同时统计 Sharpness，鼓励模型真正做出区分。

第 19.5 节：
    SkillScore = 1 - ModelLoss / NullLoss
    > 0  说明超过 Null Model
    <= 0 说明所谓高级模型还不如基础概率
"""

from __future__ import annotations

import math
from dataclasses import dataclass

# Log Loss 的概率裁剪边界：避免 log(0)
EPS = 1e-6

# 第 78 节：最小样本量与可靠度分档
MIN_SAMPLE_LOW = 20
MIN_SAMPLE_MEDIUM = 100


@dataclass
class ScoreRow:
    """一条预测-结果对。"""

    probability: float
    outcome: float
    null_probability: float | None = None


def brier(p: float, y: float) -> float:
    """第 19.1 节：BS = (p - y)²

    例：预测 80%，实际发生 → (0.8 - 1)² = 0.04
    """
    return (p - y) ** 2


def log_loss(p: float, y: float) -> float:
    """第 19.2 节：用于严厉惩罚极端错误概率。

    LL = -(y·log p + (1-y)·log(1-p))
    """
    pc = min(1.0 - EPS, max(EPS, p))
    return -(y * math.log(pc) + (1.0 - y) * math.log(1.0 - pc))


def sharpness(probabilities: list[float]) -> float:
    """第 19.4 节：预测概率的方差。

    永远预测 50% → sharpness = 0，毫无信息价值。
    """
    if not probabilities:
        return 0.0
    mean = sum(probabilities) / len(probabilities)
    return sum((p - mean) ** 2 for p in probabilities) / len(probabilities)


def mean_brier(rows: list[ScoreRow]) -> float:
    if not rows:
        return float("nan")
    return sum(brier(r.probability, r.outcome) for r in rows) / len(rows)


def mean_log_loss(rows: list[ScoreRow]) -> float:
    if not rows:
        return float("nan")
    return sum(log_loss(r.probability, r.outcome) for r in rows) / len(rows)


def skill_score(model_loss: float, null_loss: float) -> float:
    """第 19.5 节：SkillScore = 1 - ModelLoss / NullLoss

    > 0  超过 Null Model
    <= 0 不如基础概率
    """
    if null_loss <= 0:
        return float("nan")
    return 1.0 - (model_loss / null_loss)


def skill_score_from_rows(rows: list[ScoreRow]) -> float | None:
    """直接从样本计算 Skill Score（用 Brier 作为 loss）。"""
    comparable = [r for r in rows if r.null_probability is not None]
    if len(comparable) < 2:
        return None
    model_loss = mean_brier(comparable)
    null_loss = sum(brier(r.null_probability, r.outcome) for r in comparable) / len(comparable)
    return skill_score(model_loss, null_loss)


# ----------------------------------------------------------------------
# 第 19.3 节 Calibration
# ----------------------------------------------------------------------
DEFAULT_BIN_EDGES = [0.0, 0.1, 0.3, 0.5, 0.7, 0.9, 1.0]


@dataclass
class CalibrationBin:
    bin_lower: float
    bin_upper: float
    sample_count: int
    mean_predicted: float
    mean_actual: float

    @property
    def gap(self) -> float:
        """正 = 低估，负 = 过度自信。"""
        return self.mean_actual - self.mean_predicted


def calibration_curve(
    rows: list[ScoreRow], edges: list[float] | None = None
) -> list[CalibrationBin]:
    """第 19.3 节：所有标 70% 的预测，实际发生率应该接近 70%。"""
    edges = edges or DEFAULT_BIN_EDGES
    bins: list[CalibrationBin] = []

    for lo, hi in zip(edges, edges[1:]):
        members = [r for r in rows if lo <= r.probability < hi]
        if not members:
            continue
        n = len(members)
        bins.append(
            CalibrationBin(
                bin_lower=lo,
                bin_upper=hi,
                sample_count=n,
                mean_predicted=round(sum(r.probability for r in members) / n, 4),
                mean_actual=round(sum(r.outcome for r in members) / n, 4),
            )
        )
    return bins


def overconfidence_index(bins: list[CalibrationBin]) -> float:
    """第 19.3 节：正值 = 模型整体过度自信。

    例如 90% 实际只发生 76% → 明显过度自信。
    """
    weighted = [
        b for b in bins if b.mean_predicted >= 0.5 and b.sample_count > 0
    ]
    if not weighted:
        return 0.0
    total = sum(b.sample_count for b in weighted)
    return round(
        sum((b.mean_predicted - b.mean_actual) * b.sample_count for b in weighted) / total, 4
    )


# ----------------------------------------------------------------------
# 第 78 节 小样本保护
# ----------------------------------------------------------------------
def wilson_interval(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson 置信区间。小样本下比正态近似稳健得多。

    第 78 节：不能 3 次预测 3 次成功就宣布 100% 准确。
    """
    if n == 0:
        return (0.0, 0.0)
    phat = successes / n
    denom = 1 + z**2 / n
    center = (phat + z**2 / (2 * n)) / denom
    margin = (z / denom) * math.sqrt(phat * (1 - phat) / n + z**2 / (4 * n**2))
    return (max(0.0, center - margin), min(1.0, center + margin))


def reliability_label(n: int) -> str:
    """第 78 节：显示 Observed / Reliability / Sample。"""
    if n < MIN_SAMPLE_LOW:
        return "low"
    if n < MIN_SAMPLE_MEDIUM:
        return "medium"
    return "high"


@dataclass
class Aggregate:
    """一次聚合评分的完整结果。"""

    sample_size: int
    brier: float
    log_loss: float
    sharpness: float
    observed_rate: float
    mean_probability: float
    reliability: str
    ci_low: float
    ci_high: float
    skill_score: float | None = None
    null_brier: float | None = None
    bins: list[CalibrationBin] | None = None
    overconfidence: float = 0.0

    def to_dict(self) -> dict:
        def finite(v: float | None) -> float | None:
            """NaN/Inf 不是合法 JSON，统一输出 None（前端显示 —）。"""
            if v is None or not math.isfinite(v):
                return None
            return round(v, 4)

        return {
            "sample_size": self.sample_size,
            "brier": finite(self.brier),
            "log_loss": finite(self.log_loss),
            "sharpness": finite(self.sharpness),
            "observed_rate": finite(self.observed_rate),
            "mean_probability": finite(self.mean_probability),
            "reliability": self.reliability,
            "ci": [round(self.ci_low, 4), round(self.ci_high, 4)],
            "skill_score": finite(self.skill_score),
            "null_brier": finite(self.null_brier),
            "overconfidence": finite(self.overconfidence),
            "bins": [
                {
                    "bin": [b.bin_lower, b.bin_upper],
                    "n": b.sample_count,
                    "predicted": b.mean_predicted,
                    "actual": b.mean_actual,
                    "gap": round(b.gap, 4),
                }
                for b in (self.bins or [])
            ],
        }


def aggregate(rows: list[ScoreRow]) -> Aggregate:
    """一次性算出所有核心指标（第 52 节 Accuracy Lab 使用）。"""
    if not rows:
        return Aggregate(
            sample_size=0,
            brier=float("nan"),
            log_loss=float("nan"),
            sharpness=0.0,
            observed_rate=0.0,
            mean_probability=0.0,
            reliability="low",
            ci_low=0.0,
            ci_high=0.0,
        )

    n = len(rows)
    probs = [r.probability for r in rows]
    outcomes = [r.outcome for r in rows]

    # 命中数按 outcome 加权（第 18 节支持部分命中）
    hits = sum(outcomes)
    ci_low, ci_high = wilson_interval(int(round(hits)), n)

    bins = calibration_curve(rows)
    comparable = [r for r in rows if r.null_probability is not None]
    null_brier = (
        sum(brier(r.null_probability, r.outcome) for r in comparable) / len(comparable)
        if comparable
        else None
    )

    return Aggregate(
        sample_size=n,
        brier=mean_brier(rows),
        log_loss=mean_log_loss(rows),
        sharpness=sharpness(probs),
        observed_rate=hits / n,
        mean_probability=sum(probs) / n,
        reliability=reliability_label(n),
        ci_low=ci_low,
        ci_high=ci_high,
        skill_score=skill_score_from_rows(rows),
        null_brier=null_brier,
        bins=bins,
        overconfidence=overconfidence_index(bins),
    )
