"""Obsidian 导出与 Markdown 报告。

对应工程方案：
- 第 62 节 Obsidian 接入（数据库是权威源，Obsidian 是人类可读展示层）
- 第 63 节 Markdown Daily Forecast

第 62 节结构：
    XuanMirror/
    ├─ 00_仪表盘.md
    ├─ 01_本命档案.md
    ├─ 02_每日预测/
    ├─ 03_验证记录/
    ├─ 04_现实事件/
    ├─ 05_周报/
    ├─ 06_月报/
    ├─ 07_模型审计/
    └─ 08_实验/

原则：不要反过来用 Markdown 当主数据库。
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from sqlmodel import Session, select

from app.models.core import BirthProfile
from app.models.prediction import PredictionRecord
from app.models.reality import RealityEvent
from app.models.scoring import OutcomeRecord

logger = logging.getLogger("xuanmirror.export")


# ======================================================================
# 第 63 节：Markdown Daily Forecast
# ======================================================================
def daily_forecast_markdown(
    session: Session, *, user_id: int, target_date: date | None = None
) -> str:
    """生成某日的预测 Markdown（第 63 节格式）。"""
    target_date = target_date or date.today()

    rows = session.exec(
        select(PredictionRecord)
        .where(PredictionRecord.user_id == user_id)
        .where(PredictionRecord.window_start >= target_date)
        .where(PredictionRecord.window_start < target_date + timedelta(days=1))
    ).all()

    lines = [
        f"# {target_date.isoformat()} Future Forecast",
        "",
        "## 正式预测",
        "",
    ]
    if not rows:
        lines.append("_今日无正式预测。_")
    else:
        for i, r in enumerate(rows, 1):
            lines.extend(
                [
                    f"### P-{i:03d} {r.event_type}",
                    f"- 概率：{r.probability:.0%}",
                    f"- 截止：{r.window_end.date().isoformat()}",
                    f"- 状态：{r.status}",
                    f"- 描述：{r.description}",
                    "",
                    "  - 成功标准：",
                ]
            )
            for c in r.success_criteria:
                lines.append(f"    - {c}")
            lines.append("  - 失败标准：")
            for c in r.failure_criteria:
                lines.append(f"    - {c}")
            lines.append("")

    lines.append("---")
    lines.append(f"> 由玄鉴 XuanMirror 自动生成（第 63 节）。")
    return "\n".join(lines)


# ======================================================================
# 第 62 节：Obsidian Vault 导出
# ======================================================================
def export_obsidian_vault(
    session: Session, *, user_id: int, base_dir: str | Path
) -> dict[str, Any]:
    """把数据库内容导出为 Obsidian 目录结构。

    数据库是权威源；这里生成人类可读展示层。
    返回：{文件路径: 内容} 或写入磁盘。
    """
    import json

    base = Path(base_dir)
    base.mkdir(parents=True, exist_ok=True)

    profile = session.exec(
        select(BirthProfile).where(BirthProfile.user_id == user_id)
    ).first()

    written: list[str] = []

    # ---------- 00_仪表盘 ----------
    dashboard = _dashboard_md(session, user_id)
    _write(base / "00_仪表盘.md", dashboard, written)

    # ---------- 01_本命档案 ----------
    natal = _natal_md(profile)
    _write(base / "01_本命档案.md", natal, written)

    # ---------- 02_每日预测 ----------
    pred_dir = base / "02_每日预测"
    pred_dir.mkdir(exist_ok=True)
    preds = session.exec(
        select(PredictionRecord).where(PredictionRecord.user_id == user_id)
    ).all()
    for r in preds:
        md = _prediction_md(r)
        fname = f"{r.window_start.date().isoformat()}_{r.prediction_id}.md"
        _write(pred_dir / fname, md, written)

    # ---------- 03_验证记录 ----------
    ver_dir = base / "03_验证记录"
    ver_dir.mkdir(exist_ok=True)
    outcomes = session.exec(
        select(OutcomeRecord, PredictionRecord)
        .join(PredictionRecord, PredictionRecord.prediction_id == OutcomeRecord.prediction_id)  # type: ignore[arg-type]
        .where(PredictionRecord.user_id == user_id)  # type: ignore[union-attr]
    ).all()
    for out, pred in outcomes:
        md = (
            f"# {pred.prediction_id}\n\n"
            f"- 事件：{pred.event_type}\n"
            f"- 预测概率：{pred.probability:.0%}\n"
            f"- 结果：{out.outcome}\n"
            f"- 置信：{out.confidence:.0%}\n"
            f"- 判定时间：{out.judged_at.isoformat()}\n\n"
            f"## 证据\n\n{out.evidence or '（无）'}\n"
        )
        _write(ver_dir / f"{out.outcome_id}.md", md, written)

    # ---------- 04_现实事件 ----------
    ev_dir = base / "04_现实事件"
    ev_dir.mkdir(exist_ok=True)
    events = session.exec(
        select(RealityEvent).where(RealityEvent.user_id == user_id)
    ).all()
    for ev in events:
        md = (
            f"# {ev.occurred_on.isoformat()} {ev.event_type}\n\n"
            f"- 领域：{ev.domain}\n"
            f"- 来源：{ev.source}\n"
            f"- 置信：{ev.confidence:.0%}\n"
            f"- 备注：{ev.note or '（无）'}\n"
        )
        _write(ev_dir / f"{ev.occurred_on.isoformat()}_{ev.id}.md", md, written)

    # ---------- 05-08 空目录 ----------
    for d in ("05_周报", "06_月报", "07_模型审计", "08_实验"):
        (base / d).mkdir(exist_ok=True)

    logger.info("Obsidian 导出完成：%s，%d 个文件", base, len(written))
    return {"base_dir": str(base), "files": written, "count": len(written)}


# ======================================================================
def _write(path: Path, content: str, written: list[str]) -> None:
    path.write_text(content, encoding="utf-8")
    written.append(str(path))


def _dashboard_md(session: Session, user_id: int) -> str:
    from app.services.future_tree import FutureTreeBuilder

    preds = session.exec(
        select(PredictionRecord).where(PredictionRecord.user_id == user_id)
    ).all()
    verified = sum(1 for p in preds if p.status == "VERIFIED")
    frozen = sum(1 for p in preds if p.status == "FROZEN")

    lines = [
        "# 玄鉴 · 仪表盘",
        "",
        f"- 累计预测：{len(preds)}",
        f"- 已冻结：{frozen}",
        f"- 已验证：{verified}",
        "",
        "## 人生情景树（第 27 节）",
        "",
    ]
    try:
        tree = FutureTreeBuilder(session, user_id=user_id).build()
        for s in tree["scenarios"]:
            lines.append(f"- **{s['label']}**：{s['probability']:.0%} — {s['description']}")
    except Exception as exc:
        lines.append(f"_情景树生成失败：{exc}_")
    lines.append("")
    lines.append("> 数据库是权威源，本文件为人类可读展示层（第 62 节）。")
    return "\n".join(lines)


def _natal_md(profile: BirthProfile | None) -> str:
    if profile is None:
        return "# 本命档案\n\n_未登记出生档案。_"
    return (
        "# 本命档案\n\n"
        f"- 公历生日：{profile.solar_birth_date}\n"
        f"- 时辰：{profile.solar_birth_time}\n"
        f"- 时辰确定：{'是' if profile.birth_time_known else '否'}\n"
        f"- 性别：{profile.gender}\n"
        f"- 出生地：{profile.birth_place or '（未填）'}\n"
        f"- 真太阳时校正：{'开' if profile.use_true_solar_time else '关'}\n\n"
        "> 出生信息属高敏感个人数据（第 64 节），本地优先。"
    )


def _prediction_md(r: PredictionRecord) -> str:
    return (
        f"# {r.prediction_id}\n\n"
        f"- 领域：{r.domain}\n"
        f"- 事件：{r.event_type}\n"
        f"- 描述：{r.description}\n"
        f"- 概率：{r.probability:.0%}\n"
        f"- Null 基线：{(r.null_probability or 0):.0%}\n"
        f"- 窗口：{r.window_start.isoformat()} ~ {r.window_end.isoformat()}\n"
        f"- 状态：{r.status}\n"
        f"- 冻结哈希：{(r.sha256 or '')[:16]}…\n\n"
        f"## 成功标准\n\n"
        + "\n".join(f"- {c}" for c in r.success_criteria)
        + "\n\n## 失败标准\n\n"
        + "\n".join(f"- {c}" for c in r.failure_criteria)
        + "\n"
    )
