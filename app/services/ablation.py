"""Ablation Test 服务 —— 第 33 节。

    Full Model vs -Ziwei vs -Bazi vs -Qimen vs -Liuyao vs -Reality vs Null Only

判断每个模块的真实贡献。系统应允许得到「不好听」的结果：
    Reality：强贡献 / Qimen：强贡献 / Liuyao：弱贡献 /
    Ziwei：很弱贡献 / Bazi：当前无贡献

原理：
    用已验证预测的 Brier 按「是否包含某术式信号」分组对比。
    某术式摘除后 Brier 上升（变差）→ 该术式有正贡献；
    摘除后 Brier 下降（变好）→ 该术式当前是负贡献。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from app.utils import utcnow

from sqlmodel import Session, select

from app.calibration.scoring import ScoreRow, aggregate
from app.models.learning import AblationResult
from app.models.prediction import SignalRecord
from app.models.scoring import PredictionScore

# 参与消融的术式源
ABLATION_SOURCES = ["ziwei", "bazi", "qimen", "liuyao", "meihua", "reality"]

# 对应关系：摘除目标 → 需要「排除含该源信号的预测」
VARIANT_LABELS: dict[str, str] = {
    "full": "全模型",
    "null_only": "仅 Null 基线",
}


def run_ablation(session: Session, *, user_id: int | None = None) -> dict[str, Any]:
    """跑一次消融实验并落库 AblationResult。"""
    import logging

    logger = logging.getLogger("xuanmirror.ablation")

    # 1. 加载全部已验证预测
    stmt = select(PredictionScore)
    if user_id is not None:
        stmt = stmt.where(PredictionScore.user_id == user_id)
    scores = list(session.exec(stmt).all())
    if len(scores) < 3:
        return {
            "status": "insufficient_sample",
            "sample_size": len(scores),
            "note": "样本不足，无法给出可信消融结论（第 78 节）",
        }

    # 2. 每条的信号来源（用于「摘除」判断）
    sources_by_pred: dict[str, set[str]] = {}
    sig_rows = session.exec(select(SignalRecord)).all()
    for sig in sig_rows:
        pid = sig.prediction_id
        if pid:
            sources_by_pred.setdefault(pid, set()).add(sig.source_type)

    # 3. 变体计算
    variants: dict[str, list[ScoreRow]] = {"full": [], "null_only": []}
    for src in ABLATION_SOURCES:
        variants[f"-{src}"] = []

    for sc in scores:
        pid = sc.prediction_id
        srcs = sources_by_pred.get(pid, set())
        row = ScoreRow(
            probability=sc.probability,
            outcome=sc.outcome,
            null_probability=sc.null_probability,
        )
        variants["full"].append(row)
        # Null Only：只用 Null 基线概率
        if sc.null_probability is not None:
            variants["null_only"].append(
                ScoreRow(probability=sc.null_probability, outcome=sc.outcome)
            )
        # 摘除各术式
        for src in ABLATION_SOURCES:
            if src not in srcs:
                variants[f"-{src}"].append(row)

    # 4. 计算 Brier + 落库
    run_id = f"ABL-{uuid.uuid4().hex[:8]}"
    results = []
    for variant, rows in variants.items():
        if len(rows) < 3:
            continue
        agg = aggregate(rows)
        label = VARIANT_LABELS.get(variant, variant)
        results.append(
            {
                "variant": variant,
                "label": label,
                "sample_size": agg.sample_size,
                "brier": agg.brier,
                "log_loss": agg.log_loss,
                "skill_score": agg.skill_score,
            }
        )
        session.add(
            AblationResult(
                run_id=run_id,
                variant=variant,
                sample_size=agg.sample_size,
                brier=agg.brier,
                log_loss=agg.log_loss,
                skill_score=agg.skill_score,
                computed_at=utcnow(),
            )
        )
    session.commit()

    # 5. 相对 full 的贡献排序
    full_brier = next((r["brier"] for r in results if r["variant"] == "full"), None)
    if full_brier is not None:
        for r in results:
            if r["variant"] not in ("full", "null_only"):
                r["contribution"] = round(full_brier - r["brier"], 4)
        results.sort(key=lambda r: r.get("contribution", 0), reverse=True)

    logger.info("消融实验完成：%s，%d 个变体", run_id, len(results))
    return {
        "status": "ok",
        "run_id": run_id,
        "sample_size": len(scores),
        "results": results,
    }


# 便捷：仅返回结果不落库（供 API 快速展示）
def ablation_summary(session: Session, *, user_id: int | None = None) -> dict[str, Any]:
    out = run_ablation(session, user_id=user_id)
    if out.get("status") == "ok":
        out.pop("run_id", None)
    return out
