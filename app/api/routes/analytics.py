"""分析与评分路由。

对应工程方案：
- 第 19 节 评分系统
- 第 26 节 Personal Reliability Matrix
- 第 30 节 周报
- 第 31 节 月度模型审计
- 第 33 节 Ablation Test
- 第 52 节 Accuracy Lab
- 第 78 节 小样本保护
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session, select

from app.calibration.scoring import (
    Aggregate,
    ScoreRow,
    aggregate,
)
from app.database import get_session
from app.learning.reliability import ReliabilityMatrix
from app.models.scoring import PredictionScore

router = APIRouter()


# ======================================================================
# 总览（第 52 节 Accuracy Lab）
# ======================================================================
@router.get("/analytics/overall")
def overall(
    user_id: int | None = Query(None, description="不传则统计全部用户"),
    domain: str | None = None,
    time_scale: str | None = None,
    session: Session = Depends(get_session),
):
    """Brier / LogLoss / Calibration / Skill Score / Sharpness / 置信区间。"""
    rows = _load_rows(session, user_id=user_id, domain=domain, time_scale=time_scale)
    agg = aggregate(rows)
    return {"filters": {"user_id": user_id, "domain": domain, "time_scale": time_scale}, **agg.to_dict()}


# ======================================================================
# 校准曲线（第 19.3 节）
# ======================================================================
@router.get("/analytics/calibration")
def calibration(
    user_id: int | None = None,
    session: Session = Depends(get_session),
):
    """Predicted vs Actual 分桶表。前端用于画 ECharts 校准曲线。"""
    rows = _load_rows(session, user_id=user_id)
    agg = aggregate(rows)
    return {
        "bins": [
            {
                "bin": f"{b.bin_lower:.0%}-{b.bin_upper:.0%}",
                "n": b.sample_count,
                "predicted": b.mean_predicted,
                "actual": b.mean_actual,
                "gap": round(b.gap, 4),
            }
            for b in (agg.bins or [])
        ],
        "overconfidence": agg.overconfidence,
        "sample_size": agg.sample_size,
        "reliability": agg.reliability,
    }


# ======================================================================
# Personal Reliability Matrix（第 26 节）
# ======================================================================
@router.get("/analytics/reliability")
def reliability(
    user_id: int | None = None,
    session: Session = Depends(get_session),
):
    """相对 Null Model 的 predictive skill 矩阵。

    注意：这里保存的是 skill，不是命中率。
    """
    return ReliabilityMatrix(session, user_id=user_id).matrix()


# ======================================================================
# Ablation（第 33 节）
# ======================================================================
@router.get("/analytics/ablation")
def ablation(
    user_id: int | None = None,
    session: Session = Depends(get_session),
):
    """第 33 节：判断每个模块价值的消融实验（实时重算 + 落库）。

    系统应允许得到「不好听」的结果，例如：
        Reality：强贡献 / Qimen：强贡献 / Liuyao：弱贡献 /
        Ziwei：很弱贡献 / Bazi：当前无贡献
    """
    from app.services.ablation import run_ablation

    result = run_ablation(session, user_id=user_id)
    if result.get("status") == "ok":
        return {
            "status": "ok",
            "sample_size": result["sample_size"],
            "results": result["results"],
            "note": "相对 Full Model 的 Brier 差异：正值 = 该模块有正贡献",
        }
    return result


# ======================================================================
# 分组对比（按术式 / 领域 / 尺度）
# ======================================================================
@router.get("/analytics/by/{dimension}")
def by_dimension(
    dimension: str,
    user_id: int | None = None,
    session: Session = Depends(get_session),
):
    """第 52 节：按 术式 / 领域 / 时间尺度 / 规则 / Agent / 模型 / Prompt 筛选。"""
    if dimension not in {"domain", "time_scale"}:
        return {"error": f"暂不支持维度：{dimension}（骨架阶段支持 domain / time_scale）"}

    stmt = select(PredictionScore)
    if user_id is not None:
        stmt = stmt.where(PredictionScore.user_id == user_id)
    scores = session.exec(stmt).all()

    buckets: dict[str, list[ScoreRow]] = {}
    for s in scores:
        key = (s.domain if dimension == "domain" else s.time_scale) or "unknown"
        buckets.setdefault(key, []).append(
            ScoreRow(
                probability=s.probability,
                outcome=s.outcome,
                null_probability=s.null_probability,
            )
        )

    return {
        "dimension": dimension,
        "groups": {k: aggregate(v).to_dict() for k, v in buckets.items()},
    }


# ======================================================================
def _load_rows(
    session: Session,
    *,
    user_id: int | None,
    domain: str | None = None,
    time_scale: str | None = None,
) -> list[ScoreRow]:
    stmt = select(PredictionScore)
    if user_id is not None:
        stmt = stmt.where(PredictionScore.user_id == user_id)
    if domain:
        stmt = stmt.where(PredictionScore.domain == domain)
    if time_scale:
        stmt = stmt.where(PredictionScore.time_scale == time_scale)

    return [
        ScoreRow(
            probability=s.probability,
            outcome=s.outcome,
            null_probability=s.null_probability,
        )
        for s in session.exec(stmt).all()
    ]
