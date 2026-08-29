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

from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
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
# Future Tree（第 27 节）
# ======================================================================
@router.get("/future-tree")
def future_tree(
    user_id: int = Query(...),
    as_of: date | None = None,
    session: Session = Depends(get_session),
):
    """人生情景树：当前轨迹继续 / 职业变化 / 新项目重心。

    第 27 节：每周按新证据重算 P(Scenario | New Evidence)。
    """
    from app.services.future_tree import FutureTreeBuilder

    return FutureTreeBuilder(session, user_id=user_id).build(as_of=as_of)


# ======================================================================
# Counterfactual（第 28 节）
# ======================================================================
class CounterfactualIn(BaseModel):
    interventions: list[dict[str, Any]] = Field(
        default_factory=list,
        description="[{'label': '每天学习1小时', 'effects': {'study': 0.3}}]",
    )
    horizon_days: int = 365


@router.post("/counterfactual")
def counterfactual(
    user_id: int = Query(...),
    payload: CounterfactualIn | None = None,
    session: Session = Depends(get_session),
):
    """Baseline vs Intervention 对比（Decision Intelligence，第 28 节）。"""
    from app.services.counterfactual import CounterfactualEngine

    payload = payload or CounterfactualIn()
    return CounterfactualEngine(session, user_id=user_id).compare(
        interventions=payload.interventions,
        horizon_days=payload.horizon_days,
    )


# ======================================================================
# Obsidian 导出（第 62 节）
# ======================================================================
@router.get("/export/obsidian")
def export_obsidian(
    user_id: int = Query(...),
    base_dir: str = Query("./data/obsidian", description="导出目录"),
    session: Session = Depends(get_session),
):
    """数据库 → Obsidian 目录结构（数据库是权威源，Obsidian 是展示层）。"""
    from app.services.exports import export_obsidian_vault

    return export_obsidian_vault(session, user_id=user_id, base_dir=base_dir)


@router.get("/export/daily")
def export_daily(
    user_id: int = Query(...),
    target_date: date | None = None,
    session: Session = Depends(get_session),
):
    """第 63 节：Markdown Daily Forecast。"""
    from app.services.exports import daily_forecast_markdown

    return {
        "markdown": daily_forecast_markdown(
            session, user_id=user_id, target_date=target_date
        )
    }


# ======================================================================
# 周报 / 月报 / 审计（第 30 / 31 / 32 节）
# ======================================================================
@router.get("/reports/weekly")
def report_weekly(
    user_id: int = Query(...),
    session: Session = Depends(get_session),
):
    from app.services.reports import weekly_report

    return {"markdown": weekly_report(session, user_id=user_id)}


@router.get("/reports/monthly")
def report_monthly(
    user_id: int = Query(...),
    session: Session = Depends(get_session),
):
    from app.services.reports import monthly_report

    return {"markdown": monthly_report(session, user_id=user_id)}


@router.get("/reports/audit")
def report_audit(
    user_id: int = Query(...),
    session: Session = Depends(get_session),
):
    """第 32 节：第一性原理审计（10 问）。"""
    from app.services.reports import audit_report

    return audit_report(session, user_id=user_id)


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
