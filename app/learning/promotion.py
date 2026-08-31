"""Shadow Mode 与规则提升。

对应工程方案：
- 第 22 节 Prediction Error Driven Learning
- 第 24 节 禁止直接在线自修改
- 第 33 节 Ablation Test
- 第 79 节 模型版本管理

第 24 节硬性流程：

    Production Model
          │
          ├── Current Rule
          │
          └── Candidate Rule
                     ↓
                Shadow Mode
                     ↓
                50 / 100 个样本
                     ↓
            Statistical Review
                     ↓
                  Promote

核心约束：LearningAgent 不能因为一次失败就修改生产规则。
"""

from __future__ import annotations

import math
import uuid
from datetime import datetime

from app.utils import utcnow
from typing import Any

from sqlmodel import Session, select

from app.models.learning import ModelPromotion, ShadowExperiment

# 第 24 节：评审所需最小样本
DEFAULT_REVIEW_SAMPLE = 50

# 提升门槛：候选必须显著优于生产（相对改进）
MIN_RELATIVE_IMPROVEMENT = 0.02


def start_shadow_experiment(
    session: Session,
    *,
    hypothesis_id: str | None,
    name: str,
    candidate_config: dict[str, Any],
    target_sample_size: int = DEFAULT_REVIEW_SAMPLE,
    description: str = "",
    ablation_target: str | None = None,
) -> ShadowExperiment:
    """启动一个 Shadow 实验（第 24 节）。候选规则不影响生产。"""
    exp = ShadowExperiment(
        experiment_id=f"XP-{uuid.uuid4().hex[:12]}",
        hypothesis_id=hypothesis_id,
        name=name,
        description=description,
        candidate_config=candidate_config,
        target_sample_size=target_sample_size,
        status="running",
        ablation_target=ablation_target,
    )
    session.add(exp)
    session.commit()
    session.refresh(exp)
    return exp


def record_shadow_sample(
    session: Session,
    *,
    experiment_id: str,
    candidate_brier: float | None = None,
    production_brier: float | None = None,
) -> ShadowExperiment:
    """累加 Shadow 样本。达到目标后自动进入 reviewing。"""
    exp = session.exec(
        select(ShadowExperiment).where(ShadowExperiment.experiment_id == experiment_id)
    ).first()
    if exp is None:
        raise KeyError(f"未知实验：{experiment_id}")

    exp.current_sample_size += 1
    if candidate_brier is not None:
        # 增量均值
        prev = exp.candidate_brier
        exp.candidate_brier = (
            candidate_brier if prev is None else _running_mean(prev, exp.current_sample_size - 1, candidate_brier)
        )
    if production_brier is not None:
        prev = exp.production_brier
        exp.production_brier = (
            production_brier
            if prev is None
            else _running_mean(prev, exp.current_sample_size - 1, production_brier)
        )

    if exp.current_sample_size >= exp.target_sample_size and exp.status == "running":
        exp.status = "reviewing"

    session.add(exp)
    session.commit()
    session.refresh(exp)
    return exp


def review_experiment(
    session: Session, *, experiment_id: str, auto_promote: bool = False
) -> dict[str, Any]:
    """统计评审（第 24 节）。样本不足或改进不显著则拒绝提升。"""
    exp = session.exec(
        select(ShadowExperiment).where(ShadowExperiment.experiment_id == experiment_id)
    ).first()
    if exp is None:
        raise KeyError(f"未知实验：{experiment_id}")

    n = exp.current_sample_size
    if n < exp.target_sample_size:
        return {
            "experiment_id": experiment_id,
            "verdict": "insufficient_sample",
            "sample": n,
            "required": exp.target_sample_size,
            "note": f"样本不足（{n}/{exp.target_sample_size}），不得提升（第 24 节）",
        }

    if exp.candidate_brier is None or exp.production_brier is None:
        return {
            "experiment_id": experiment_id,
            "verdict": "insufficient_data",
            "note": "缺少候选或生产的 Brier，无法评审",
        }

    improvement = (exp.production_brier - exp.candidate_brier) / max(1e-9, exp.production_brier)
    # 简化的配对检验：以样本量估计标准误
    se = math.sqrt(max(1e-9, 0.25 / n))
    z = (exp.production_brier - exp.candidate_brier) / max(1e-9, se)
    p_value = _normal_sf(abs(z)) * 2

    passed = improvement >= MIN_RELATIVE_IMPROVEMENT and p_value < 0.05

    if passed and auto_promote:
        exp.status = "promoted"
    elif not passed:
        exp.status = "rejected"
        exp.review_note = (
            f"改进 {improvement:.2%}（门槛 {MIN_RELATIVE_IMPROVEMENT:.0%}），"
            f"p={p_value:.3f} —— 不提升"
        )
    else:
        exp.status = "reviewing"
        exp.review_note = f"通过评审（改进 {improvement:.2%}, p={p_value:.3f}），等待提升"

    session.add(exp)
    session.commit()

    return {
        "experiment_id": experiment_id,
        "verdict": "passed" if passed else "rejected",
        "sample": n,
        "production_brier": round(exp.production_brier, 4),
        "candidate_brier": round(exp.candidate_brier, 4),
        "improvement": round(improvement, 4),
        "p_value": round(p_value, 4),
        "status": exp.status,
    }


def promote(
    session: Session,
    *,
    experiment_id: str,
    component: str,
    component_id: str,
    from_version: str,
    to_version: str,
    promoted_by: str = "system",
) -> ModelPromotion:
    """正式提升（第 24 / 79 节）。"""
    exp = session.exec(
        select(ShadowExperiment).where(ShadowExperiment.experiment_id == experiment_id)
    ).first()
    if exp is None:
        raise KeyError(f"未知实验：{experiment_id}")
    if exp.status not in {"reviewing", "promoted"}:
        raise ValueError(
            f"实验状态为 {exp.status}，不得提升（第 24 节：必须先通过统计评审）"
        )

    promotion = ModelPromotion(
        experiment_id=experiment_id,
        component=component,
        component_id=component_id,
        from_version=from_version,
        to_version=to_version,
        sample_size=exp.current_sample_size,
        brier_before=exp.production_brier,
        brier_after=exp.candidate_brier,
        improvement=(
            None
            if (exp.production_brier is None or exp.candidate_brier is None)
            else (exp.production_brier - exp.candidate_brier) / max(1e-9, exp.production_brier)
        ),
        promoted_by=promoted_by,
    )
    session.add(promotion)

    exp.status = "promoted"
    session.add(exp)
    session.commit()
    session.refresh(promotion)
    return promotion


def check_regression(
    session: Session, *, component_id: str, current_brier: float
) -> bool:
    """第 79 节：升级后性能下降 → 自动 Regression Alert。"""
    last = session.exec(
        select(ModelPromotion)
        .where(ModelPromotion.component_id == component_id)
        .order_by(ModelPromotion.promoted_at.desc())  # type: ignore[union-attr]
    ).first()
    if last is None or last.brier_after is None:
        return False

    regressed = current_brier > last.brier_after
    if regressed:
        last.regression_alert = True
        last.rolled_back_at = utcnow()
        session.add(last)
        session.commit()
    return regressed


# ----------------------------------------------------------------------
def _running_mean(prev: float, n: int, new_value: float) -> float:
    return (prev * n + new_value) / (n + 1)


def _normal_sf(x: float) -> float:
    """标准正态上尾概率（对数互补误差函数近似）。"""
    return 0.5 * math.erfc(x / math.sqrt(2))
