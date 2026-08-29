"""后台调度器 —— 第 58 节 Scheduler。

时间表（可配置，第 58 节允许用户修改）：

    23:30  更新 Reality State（第 10 节）
    23:40  Future Scanner（第 3.2 节）
    23:45  术数计算（第 6 节）
    23:50  多 Agent + 对抗审查（第 12 / 21 节）
    23:55  冻结明日预测（第 16 节）
    次日晚  自动进入验证队列并提醒（第 59 节）

实现：APScheduler BackgroundScheduler。每个 job 独立开 Session。
SCHEDULER_ENABLED=false 时不启动（默认关闭，避免开发机空转）。
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Callable

from apscheduler.schedulers.background import BackgroundScheduler
from sqlmodel import Session, select

from app.config import Settings, get_settings
from app.models.core import User
from app.models.prediction import PredictionRecord
from app.schemas.prediction import PredictionStatus

logger = logging.getLogger("xuanmirror.scheduler")

# job 函数签名：接收 engine，自行开 Session（线程安全）
JobFn = Callable[[object], None]


# ======================================================================
# Job 实现
# ======================================================================
def _user_ids(session: Session) -> list[int]:
    return [u.id for u in session.exec(select(User).where(User.is_active.is_(True))).all() if u.id]  # type: ignore[union-attr]


def job_update_reality(engine: object) -> None:
    """第 58 节 23:30：对所有活跃用户更新 Reality State。"""
    from app.reality.state import persist_daily_state

    with Session(engine) as session:  # type: ignore[arg-type]
        for uid in _user_ids(session):
            persist_daily_state(session, user_id=uid)
            logger.info("reality state 已更新：user=%s", uid)


def job_daily_pipeline(engine: object) -> None:
    """第 58 节 23:40-23:55：扫描 → 盲审 → 融合 → 对抗审查 → 预算 → 冻结。"""
    from app.services.pipeline import DailyPipeline

    target = date.today() + timedelta(days=1)  # 冻结明日预测

    with Session(engine) as session:  # type: ignore[arg-type]
        for uid in _user_ids(session):
            # limit 折中：免费模型池单次调用 5-30s，20 候选 × 2 LLM Agent
            # 会跑 10+ 分钟。8 候选足以满足 PRED-01（≥3 条正式预测）。
            result = DailyPipeline(session, user_id=uid).run(
                target_date=target, scale="day", limit=8
            )
            logger.info(
                "每日预测完成：user=%s target=%s 冻结=%d 候选=%d 拦截=%d",
                uid, target, len(result.frozen), len(result.candidates), len(result.rejected),
            )


def job_verify_reminder(engine: object) -> None:
    """第 59 节 次日晚：今天到期预测进入 VERIFY_REQUIRED，等待用户验证。

    注意：不是「已经到期才提醒」，而是「今天到期今晚提醒」——
    否则 21:00 运行时窗口（23:59 结束）还没到，永远提醒不出来。
    """
    now = datetime.utcnow()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + timedelta(days=1)

    with Session(engine) as session:  # type: ignore[arg-type]
        stmt = (
            select(PredictionRecord)
            .where(PredictionRecord.status == PredictionStatus.FROZEN.value)
            .where(PredictionRecord.verification_due_at >= today_start)  # type: ignore[union-attr]
            .where(PredictionRecord.verification_due_at < today_end)  # type: ignore[union-attr]
        )
        rows = session.exec(stmt).all()
        for row in rows:
            row.status = PredictionStatus.VERIFY_REQUIRED.value
        session.commit()
        logger.info("验证提醒：%d 条今天到期的预测进入 VERIFY_REQUIRED", len(rows))


# ======================================================================
# Scheduler 构建
# ======================================================================
def build_scheduler(engine: object, settings: Settings | None = None) -> BackgroundScheduler | None:
    """按配置构建调度器。未启用时返回 None。

    SCHEDULER_ENABLED=false 时返回 None —— 开发环境默认关闭，
    避免 23:55 自动跑模型烧 token。
    """
    settings = settings or get_settings()
    if not settings.SCHEDULER_ENABLED:
        logger.info("调度器未启用（SCHEDULER_ENABLED=false）")
        return None

    def _cron(hhmm: str) -> dict[str, int]:
        h, m = hhmm.split(":")
        return {"hour": int(h), "minute": int(m)}

    scheduler = BackgroundScheduler(timezone=settings.XUANMIRROR_TIMEZONE)

    scheduler.add_job(
        job_update_reality, "cron", args=[engine],
        **{"hour": 23, "minute": 30}, id="reality_update",
    )
    scheduler.add_job(
        job_daily_pipeline, "cron", args=[engine],
        **{"hour": 23, "minute": 40}, id="daily_pipeline",
    )
    scheduler.add_job(
        job_verify_reminder, "cron", args=[engine],
        **{"hour": 21, "minute": 0}, id="verify_reminder",
    )

    logger.info(
        "调度器已构建：%s",
        {j.id: str(j.trigger) for j in scheduler.get_jobs()},
    )
    return scheduler


def start_scheduler(engine: object) -> BackgroundScheduler | None:
    """启动调度器（幂等：已运行则返回现有实例）。"""
    scheduler = build_scheduler(engine)
    if scheduler is not None and not scheduler.running:
        scheduler.start()
    return scheduler
