"""周报 / 月报 / 审计报告。

对应工程方案：
- 第 30 节 周报
- 第 31 节 月度模型审计
- 第 32 节 第一性原理审计 Agent

第 30 节周报必须包含：
    正式预测数 / 可验证 / 不可验证 / Brier / Null Brier / Skill Score /
    最佳 / 最弱 / 发现 / 异常 / 建议

实现：确定性统计为骨架，ReportAgent（LLM）增强叙事。
LLM 不可用时返回统计版（仍完整可读）。
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Any

from sqlmodel import Session, select

from app.agents.base import AgentContext
from app.agents.learning_agents import FirstPrinciplesAuditAgent, ReportAgent
from app.calibration.scoring import aggregate
from app.models.prediction import PredictionRecord
from app.models.scoring import OutcomeRecord, PredictionScore

logger = logging.getLogger("xuanmirror.reports")


# ======================================================================
# 统计骨架
# ======================================================================
def _stats(session: Session, *, user_id: int, start: date, end: date) -> dict[str, Any]:
    """指定周期的统计（周报/月报共用）。"""
    start_dt = datetime(start.year, start.month, start.day)
    end_dt = datetime(end.year, end.month, end.day, 23, 59, 59)

    preds = session.exec(
        select(PredictionRecord)
        .where(PredictionRecord.user_id == user_id)
        .where(PredictionRecord.window_start >= start_dt)
        .where(PredictionRecord.window_start <= end_dt)
    ).all()

    outcomes = session.exec(
        select(PredictionScore)
        .where(PredictionScore.user_id == user_id)
        .where(PredictionScore.scored_at >= start_dt)
        .where(PredictionScore.scored_at <= end_dt)
    ).all()

    verified = sum(1 for p in preds if p.status == "VERIFIED")
    unverified = len(preds) - verified

    scores = [
        {
            "probability": s.probability,
            "outcome": s.outcome,
            "null_probability": s.null_probability,
        }
        for s in outcomes
    ]

    agg = _agg_from_dicts(scores) if scores else None

    # 按 source 分组成绩（第 30 节：最佳/最弱）
    return {
        "period": [start.isoformat(), end.isoformat()],
        "total_predictions": len(preds),
        "verified": verified,
        "unverifiable": unverified,
        "sample_size": len(scores),
        "brier": agg["brier"] if agg else None,
        "null_brier": agg["null_brier"] if agg else None,
        "skill_score": agg["skill_score"] if agg else None,
        "overconfidence": agg["overconfidence"] if agg else 0.0,
        "hits": agg["hits"] if agg else None,
        "per_domain": _per_domain(outcomes),
    }


def _agg_from_dicts(rows: list[dict[str, Any]]) -> dict[str, Any]:
    from app.calibration.scoring import ScoreRow, aggregate

    rs = [
        ScoreRow(
            probability=r["probability"],
            outcome=r["outcome"],
            null_probability=r.get("null_probability"),
        )
        for r in rows
    ]
    a = aggregate(rs)
    return {
        "brier": a.brier,
        "null_brier": a.null_brier,
        "skill_score": a.skill_score,
        "overconfidence": a.overconfidence,
        "hits": int(round(a.observed_rate * a.sample_size)),
        "sample": a.sample_size,
    }


def _per_domain(scores: list[PredictionScore]) -> dict[str, float]:
    """按领域聚合 Brier。"""
    buckets: dict[str, list[float]] = {}
    for s in scores:
        buckets.setdefault(s.domain or "unknown", []).append(
            (s.probability - s.outcome) ** 2
        )
    return {k: round(sum(v) / len(v), 4) for k, v in buckets.items()}


# ======================================================================
# 周报（第 30 节）
# ======================================================================
def weekly_report(session: Session, *, user_id: int) -> str:
    end = date.today()
    start = end - timedelta(days=7)
    stats = _stats(session, user_id=user_id, start=start, end=end)

    # LLM 叙事增强（失败则用统计版）
    narrative = _llm_narrative(session, user_id, "weekly", stats)
    if narrative:
        return narrative

    return _stats_markdown("周报", stats)


# ======================================================================
# 月报（第 31 节月度模型审计）
# ======================================================================
def monthly_report(session: Session, *, user_id: int) -> str:
    end = date.today()
    start = end - timedelta(days=30)
    stats = _stats(session, user_id=user_id, start=start, end=end)

    narrative = _llm_narrative(session, user_id, "monthly", stats)
    if narrative:
        return narrative

    return _stats_markdown("月报", stats)


def audit_report(session: Session, *, user_id: int) -> dict[str, Any]:
    """第 32 节：第一性原理审计（10 问）。"""
    stats = _stats(session, user_id=user_id, start=date.today() - timedelta(days=30), end=date.today())

    ctx = AgentContext(
        user_id=user_id,
        session=session,
        payload={"stats": stats},
    )
    try:
        result = FirstPrinciplesAuditAgent().run(ctx)
        if result.ok and result.output.get("answers"):
            return {
                "status": "ok",
                "answers": result.output["answers"],
                "verdict": result.output.get("verdict", ""),
            }
    except Exception as exc:
        logger.warning("审计 Agent 失败：%s", exc)

    # 确定性兜底
    answers = []
    for i, q in enumerate(FirstPrinciplesAuditAgent.AUDIT_QUESTIONS, 1):
        answers.append(
            {
                "question": q,
                "answer": _deterministic_answer(q, stats),
                "evidence": "确定性统计（LLM 不可用）",
                "severity": "info",
            }
        )
    return {"status": "deterministic", "answers": answers, "verdict": "审计基于统计骨架，建议在 LLM 可用时重跑"}


# ======================================================================
def _llm_narrative(session: Session, user_id: int, period: str, stats: dict[str, Any]) -> str | None:
    ctx = AgentContext(
        user_id=user_id,
        session=session,
        payload={"stats": stats, "period": period},
    )
    try:
        result = ReportAgent().run(ctx)
        if result.ok and result.output.get("summary"):
            out = result.output
            lines = [
                f"# 玄鉴 {period} 报告",
                "",
                f"**{out.get('title', '')}**",
                "",
                out.get("summary", ""),
                "",
                "## 亮点",
            ]
            lines += [f"- {h}" for h in out.get("highlights", [])]
            lines += ["", "## 最弱环节"]
            lines += [f"- {w}" for w in out.get("weakest", [])]
            lines += ["", "## 发现"]
            lines += [f"- {f}" for f in out.get("findings", [])]
            lines += ["", "## 异常"]
            lines += [f"- {a}" for a in out.get("anomalies", [])]
            lines += ["", "## 建议"]
            lines += [f"- {r}" for r in out.get("recommendations", [])]
            return "\n".join(lines)
    except Exception as exc:
        logger.warning("报告 Agent 失败：%s", exc)
    return None


def _stats_markdown(title: str, stats: dict[str, Any]) -> str:
    """确定性统计版报告（LLM 不可用时）。"""
    b = stats.get("brier")
    nb = stats.get("null_brier")
    skill = stats.get("skill_score")

    lines = [
        f"# 玄鉴 {title}",
        "",
        f"- 周期：{stats['period'][0]} ~ {stats['period'][1]}",
        f"- 正式预测：{stats['total_predictions']}",
        f"- 可验证：{stats['verified']}",
        f"- 不可验证：{stats['unverifiable']}",
        f"- 已评分样本：{stats['sample_size']}",
        "",
        "## 概率质量",
        "",
        f"- Brier：{b:.4f}" if b is not None else "- Brier：样本不足",
        f"- Null Brier：{nb:.4f}" if nb is not None else "- Null Brier：样本不足",
        f"- Skill Score：{skill:+.1%}" if skill is not None else "- Skill Score：样本不足",
        f"- 过度自信指数：{stats['overconfidence']:+.3f}",
        "",
        "## 分领域 Brier",
        "",
    ]
    for domain, br in sorted(stats.get("per_domain", {}).items(), key=lambda x: x[1]):
        lines.append(f"- {domain}：{br:.4f}")
    lines.append("")
    lines.append("> 确定性统计版（LLM 报告 Agent 不可用时生成，第 30/31 节）")
    return "\n".join(lines)


def _deterministic_answer(question: str, stats: dict[str, Any]) -> str:
    """第 32 节 10 问的统计回答。"""
    skill = stats.get("skill_score")
    if "基础概率" in question:
        return f"样本 {stats['sample_size']}，Skill {skill:+.1%}" if skill is not None else "样本不足"
    if "现实数据" in question:
        return "需 Ablation 数据（见实验室页）"
    if "伪相关" in question or "连续失败" in question:
        return "需累积更多验证样本（第 78 节小样本保护）"
    if "解释" in question:
        return "默认存在此风险，靠对抗性 Gate 与冻结哈希约束"
    return "基于统计骨架，待 LLM 审计增强"
