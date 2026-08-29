"""验证后学习闭环。

对应工程方案：
- 第 22 节 Prediction Error Driven Learning
- 第 23 节 失败归因
- 第 24 节 禁止直接在线自修改（Shadow Mode）
- 第 25 节 Rule Registry 统计
- 第 26 节 Personal Reliability Matrix（回喂 Fusion）
- 第 61 节 Reality Event Ledger

第 22 节核心：
    预测失败不是异常。预测失败是训练数据。

流程（每次验证后执行）：
    Outcome → 归因（AttributionAgent + 确定性兜底）→ 假设落库 →
    Shadow 样本累积 → 规则增益统计 → 可靠度矩阵更新 → 回喂 Fusion

第 24 节硬性约束：
    不直接改生产规则。全部走 Shadow Mode → 统计评审 → Promote。
"""

from __future__ import annotations

import logging
from typing import Any

from sqlmodel import Session, select

from app.agents.learning_agents import AttributionAgent
from app.agents.base import AgentContext
from app.calibration.scoring import brier
from app.models.learning import LearningHypothesis, ShadowExperiment
from app.models.prediction import PredictionRecord, SignalRecord
from app.models.registry import RuleMetric
from app.models.scoring import PredictionScore
from app.schemas.signal import SourceType

logger = logging.getLogger("xuanmirror.learning")


# ======================================================================
# 确定性归因兜底（LLM 不可用时仍能给出可对冲假设，第 23 节）
# ======================================================================
def deterministic_attribution(
    *,
    probability: float,
    outcome: float,
    null_probability: float | None,
    signals: list[SignalRecord],
) -> list[dict[str, Any]]:
    """无 LLM 时的规则化归因。

    第 23 节要求假设必须可对冲、指向具体对象。
    """
    hypotheses: list[dict[str, Any]] = []
    error = outcome - probability  # >0 低估，<0 过度自信

    if error < -0.15:
        hypotheses.append({
            "id": "H1",
            "statement": f"模型过度自信：预测 {probability:.2f}，实际 {outcome:.2f}",
            "category": "overconfidence",
            "target_system": None,
            "target_domain": None,
            "target_time_scale": None,
            "target_rule_ids": [],
        })

    # 相关证据重复计权（第 20.12 节）：多个同依赖组信号
    groups: dict[str, list[str]] = {}
    for sig in signals:
        key = sig.dependency_group or f"solo:{sig.source_type}"
        groups.setdefault(key, []).append(sig.source_type)
    correlated = {g: s for g, s in groups.items() if len(s) > 1}
    if correlated:
        hypotheses.append({
            "id": "H2",
            "statement": f"相关证据重复计权：{list(correlated)} 组信号并非独立证据",
            "category": "correlated_evidence",
            "target_system": list(correlated)[0],
            "target_domain": None,
            "target_time_scale": None,
            "target_rule_ids": [],
        })

    # Reality 反对但被忽略（第 23 节 H3）
    reality = next((s for s in signals if s.source_type == SourceType.REALITY.value), None)
    if reality is not None and reality.direction < 0 and probability > 0.6:
        hypotheses.append({
            "id": "H3",
            "statement": "Reality 信号明显反对，但 Fusion 权重不足",
            "category": "fusion_weight",
            "target_system": "reality",
            "target_domain": reality.domain,
            "target_time_scale": reality.time_scale,
            "target_rule_ids": [],
        })

    # Null 基线对比（第 23 节：若与 Null 无差异，说明术数无增量）
    if null_probability is not None and abs(probability - null_probability) < 0.05:
        hypotheses.append({
            "id": "H4",
            "statement": f"预测 {probability:.2f} 与 Null 基线 {null_probability:.2f} 几乎无差异，"
                         f"术数信号未提供增量信息",
            "category": "baseline_only",
            "target_system": None,
            "target_domain": None,
            "target_time_scale": None,
            "target_rule_ids": [],
        })

    return hypotheses


# ======================================================================
# 主流程：验证后学习
# ======================================================================
def run_learning_after_verify(
    session: Session, *, prediction_id: str, user_id: int
) -> dict[str, Any]:
    """Outcome 判定后执行完整学习闭环。

    幂等：同一预测只学习一次（已有 LearningHypothesis 则跳过）。
    """
    from app.models.scoring import OutcomeRecord

    score = session.exec(
        select(PredictionScore).where(PredictionScore.prediction_id == prediction_id)
    ).first()
    if score is None:
        return {"status": "skipped", "reason": "无评分记录"}

    outcome = score.outcome
    probability = score.probability
    null_prob = score.null_probability

    pred = session.exec(
        select(PredictionRecord).where(PredictionRecord.prediction_id == prediction_id)
    ).first()
    signals = session.exec(
        select(SignalRecord).where(SignalRecord.prediction_id == prediction_id)
    ).all() if pred else []

    # 幂等检查
    existing = session.exec(
        select(LearningHypothesis).where(
            LearningHypothesis.prediction_id == prediction_id
        )
    ).first()
    if existing:
        return {"status": "skipped", "reason": "已学习过"}

    # ---------- 1. 归因（LLM + 确定性兜底）----------
    hypotheses: list[dict[str, Any]] = []
    if pred is not None:
        ctx = AgentContext(
            user_id=user_id,
            session=session,
            target_event=pred.event_type,
            domain=pred.domain,
            prediction_id=prediction_id,
            payload={
                "prediction": {
                    "event_type": pred.event_type,
                    "probability": probability,
                    "outcome": outcome,
                    "success_criteria": pred.success_criteria,
                },
                "signals": [s.model_dump(mode="json") for s in signals],
            },
        )
        try:
            result = AttributionAgent().run(ctx)
            if result.ok:
                hypotheses = result.output.get("hypotheses", [])
        except Exception as exc:
            logger.warning("AttributionAgent 失败：%s", exc)

    if not hypotheses:
        hypotheses = deterministic_attribution(
            probability=probability,
            outcome=outcome,
            null_probability=null_prob,
            signals=signals,
        )

    # ---------- 2. 假设落库（第 23 节）----------
    for h in hypotheses:
        session.add(
            LearningHypothesis(
                hypothesis_id=f"HY-{prediction_id[-8:]}-{h.get('id', 'H')}",
                prediction_id=prediction_id,
                statement=h.get("statement", ""),
                category=h.get("category", "other"),
                target_system=h.get("target_system"),
                target_domain=h.get("target_domain"),
                target_time_scale=h.get("target_time_scale"),
                target_rule_ids=h.get("target_rule_ids", []),
                status="proposed",
            )
        )
    session.commit()

    # ---------- 3. 规则增益统计（第 25 节）----------
    brier_val = brier(probability, outcome)
    for sig in signals:
        for rule_id in (sig.rule_ids or []):
            metric = session.exec(
                select(RuleMetric).where(RuleMetric.rule_id == rule_id)
            ).first()
            if metric is None:
                metric = RuleMetric(rule_id=rule_id)
                session.add(metric)
            # 增量均值
            n = metric.call_count
            metric.mean_gain = (metric.mean_gain * n + brier_val) / (n + 1)
            metric.call_count = n + 1
    session.commit()

    # ---------- 4. Shadow 样本累积（第 24 节：禁止直接在线自修改）----------
    for h in hypotheses:
        target_rule = (h.get("target_rule_ids") or [None])[0]
        if target_rule:
            exp = session.exec(
                select(ShadowExperiment).where(
                    ShadowExperiment.name == f"shadow:{target_rule}"
                )
            ).first()
            if exp is None:
                from app.learning.promotion import start_shadow_experiment

                exp = start_shadow_experiment(
                    session,
                    hypothesis_id=None,
                    name=f"shadow:{target_rule}",
                    candidate_config={"rule_id": target_rule},
                    description=f"规则 {target_rule} 的 Shadow 验证",
                )
            from app.learning.promotion import record_shadow_sample

            record_shadow_sample(
                session, experiment_id=exp.experiment_id, candidate_brier=brier_val
            )

    return {
        "status": "learned",
        "hypotheses": len(hypotheses),
        "brier": round(brier_val, 4),
        "shadow_samples": len(hypotheses),
    }
