"""天气校准健身房 —— 阴性对照域（2026-09-26 round 28）。

目的（见对话评审结论）：
    1. 概率机器（Brier / 校准 bins / 可靠度矩阵）在零争议、机械判定的域上
       高频喂样本，机器层 bug 几天内暴露，而不是三个月后污染个人域对账单；
    2. 阴性对照：术式在纯物理随机-looking 域上若"跑赢"Null，优先怀疑泄漏
       而非奇迹（C-006）。

纪律（预注册，不得随结果调整）：
    - 每天恰好 2 个事件类型：降水（≥0.1mm）/ 高温（≥气候中位数）；
    - Null = Open-Meteo archive 十年同期 ±7 天气候基线；
    - 只有 Null 概率落在 [0.15, 0.85] 的事件才入选（edge 可判定性前置承诺）；
    - 判定零人工裁量：实测值 vs 阈值，evidence 带实测数；
    - 样本带 provenance 溯源标（live / backfill / mechanical），
      回填样本只作校准种子与引擎体检，与 live 分开统计。
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from sqlmodel import Session, select

from app.config import get_settings
from app.core.weather.provider import ClimoStats, OpenMeteoProvider, WeatherProviderError
from app.models.prediction import PredictionRecord
from app.models.scoring import OutcomeRecord
from app.schemas.outcome import Outcome
from app.schemas.prediction import PredictionCandidate, PredictionStatus, TimeScale
from app.schemas.signal import Domain, Evidence, EvidenceSource, Signal, SourceType, TimeWindow

logger = logging.getLogger("xuanmirror.weather_gym")

WEATHER_EVENT_PRECIP = "weather.precip"
WEATHER_EVENT_TEMP_HIGH = "weather.temp_high"
PRECIP_THRESHOLD_MM = 0.1
TEMP_QUANTILE = 0.5  # 高温阈 = 气候 50 分位 → Null ≈ 0.5，可判定性最强
NULL_RANGE = (0.15, 0.85)  # Null 概率预注册入选区间
GRADING_RULE = "机械二值：Open-Meteo 实测值对预注册阈值判定，无人工裁量"


@dataclass(frozen=True)
class WeatherCandidateSpec:
    """一天的候选事件（冻结前 fully pre-registered）。"""

    event_type: str
    description: str
    probability: float
    success_criteria: list[str]
    failure_criteria: list[str]
    threshold_text: str


# ----------------------------------------------------------------------
# 候选构建（确定性：同日期同气候 → 同候选）
# ----------------------------------------------------------------------
def build_candidates(target: date, stats: ClimoStats, city: str) -> list[WeatherCandidateSpec]:
    weekday_zh = "一二三四五六日"[target.weekday()]
    date_label = f"{city} {target.month}月{target.day}日（周{weekday_zh}）"
    specs: list[WeatherCandidateSpec] = []

    p_precip = stats.precip_ge_threshold_prob
    if NULL_RANGE[0] <= p_precip <= NULL_RANGE[1]:
        specs.append(
            WeatherCandidateSpec(
                event_type=WEATHER_EVENT_PRECIP,
                description=f"{date_label}有降水（日降水量≥{PRECIP_THRESHOLD_MM}mm）",
                probability=round(p_precip, 4),
                success_criteria=[f"实测日降水量≥{PRECIP_THRESHOLD_MM}mm"],
                failure_criteria=[f"实测日降水量<{PRECIP_THRESHOLD_MM}mm"],
                threshold_text=f"{PRECIP_THRESHOLD_MM}mm",
            )
        )

    t_threshold = stats.tmax_quantiles.get(TEMP_QUANTILE)
    if t_threshold is not None:
        p_temp = 1.0 - TEMP_QUANTILE  # ≥50 分位的理论概率
        if NULL_RANGE[0] <= p_temp <= NULL_RANGE[1]:
            specs.append(
                WeatherCandidateSpec(
                    event_type=WEATHER_EVENT_TEMP_HIGH,
                    description=f"{date_label}最高气温≥{t_threshold}°C",
                    probability=round(p_temp, 4),
                    success_criteria=[f"实测日最高气温≥{t_threshold}°C"],
                    failure_criteria=[f"实测日最高气温<{t_threshold}°C"],
                    threshold_text=f"{t_threshold}°C",
                )
            )
    return specs


def _null_signal(spec: WeatherCandidateSpec, window: TimeWindow) -> Signal:
    """气候基线 Signal。direction=0（Null 不表达倾向），strength=基线概率。"""
    return Signal(
        source=SourceType.NULL,
        domain=Domain.WEATHER,
        target_event=spec.event_type,
        direction=0.0,
        strength=spec.probability,
        confidence=0.6,
        time_window=window,
        time_scale=TimeScale.DAY,
        evidence=[
            Evidence(
                source=EvidenceSource.EXTERNAL_DATA,
                description=(
                    f"Open-Meteo archive 2015-2024 同期±7天气候基线："
                    f"P={spec.probability:.2f}"
                ),
            )
        ],
        engine_version="openmeteo-climatology-0.1.0",
    )


def _window(target: date) -> TimeWindow:
    return TimeWindow(
        start=datetime.combine(target, time.min),
        end=datetime.combine(target, time.max),
    )


# ----------------------------------------------------------------------
# Provider 构造
# ----------------------------------------------------------------------
def _provider(transport=None) -> OpenMeteoProvider:
    s = get_settings()
    return OpenMeteoProvider(
        s.XUANMIRROR_WEATHER_LAT, s.XUANMIRROR_WEATHER_LON, transport=transport
    )


# ----------------------------------------------------------------------
# 冻结（复用 DailyPipeline._freeze，含 sha256 / freeze 快照 / 信号落库）
# ----------------------------------------------------------------------
def _freeze_candidates(
    session: Session,
    user_id: int,
    target: date,
    specs: list[WeatherCandidateSpec],
    *,
    status: str,
    provenance: str,
) -> list[str]:
    if not specs:
        return []
    from app.services.pipeline import DailyPipeline

    pipe = DailyPipeline(session, user_id=user_id)
    frozen: list[str] = []
    for spec in specs:
        cand = PredictionCandidate(
            domain=Domain.WEATHER,
            event_type=spec.event_type,
            description=spec.description,
            probability=spec.probability,
            time_scale=TimeScale.DAY,
            window_start=_window(target).start,
            window_end=_window(target).end,
            success_criteria=spec.success_criteria,
            failure_criteria=spec.failure_criteria,
            grading_rule=GRADING_RULE,
            signals=[_null_signal(spec, _window(target))],
            # 健身房车道绕过个人域预算（第 4 节预算保护的是个人事件撒网，
            # 天气域每日固定 2 事件已预注册，不存在多重比较膨胀）
            budget_granted=True,
        )
        pred = pipe._freeze(cand, status=status, provenance=provenance)
        if pred is None:
            logger.warning("天气候选冻结失败：%s %s", target, spec.event_type)
            continue
        frozen.append(pred.prediction_id)
    session.commit()
    return frozen


def _existing_event_types(session: Session, user_id: int, target: date) -> set[str]:
    day_start = datetime.combine(target, time.min)
    rows = session.exec(
        select(PredictionRecord).where(
            PredictionRecord.user_id == user_id,
            PredictionRecord.domain == Domain.WEATHER.value,
            PredictionRecord.window_start >= day_start,
            PredictionRecord.window_start < day_start + timedelta(days=1),
        )
    ).all()
    return {r.event_type for r in rows}


# ----------------------------------------------------------------------
# 机械判定（零人工裁量）
# ----------------------------------------------------------------------
_TEMP_RE = re.compile(r"≥\s*(-?\d+(?:\.\d+)?)°C")


def _judge_mechanical(spec_event_type: str, success_criteria: list[str], actual: "DayWeatherLike") -> tuple[float, str] | None:
    """返回 (outcome, evidence)；实测缺失返回 None（不判定，诚实跳过）。"""
    if actual.precipitation_mm is None or actual.tmax_c is None:
        return None
    actual_text = f"降水 {actual.precipitation_mm:.1f}mm / 最高温 {actual.tmax_c:.1f}°C"
    if spec_event_type == WEATHER_EVENT_PRECIP:
        hit = actual.precipitation_mm >= PRECIP_THRESHOLD_MM
        return (1.0 if hit else 0.0), f"机械判定：{actual_text}，阈值 ≥{PRECIP_THRESHOLD_MM}mm"
    if spec_event_type == WEATHER_EVENT_TEMP_HIGH:
        m = _TEMP_RE.search(success_criteria[0]) if success_criteria else None
        if m is None:
            return None
        threshold = float(m.group(1))
        hit = actual.tmax_c >= threshold
        return (1.0 if hit else 0.0), f"机械判定：{actual_text}，阈值 ≥{threshold}°C"
    return None


class DayWeatherLike:
    """actual_daily 行的最小协议（DayWeather duck type）。"""

    precipitation_mm: float | None
    tmax_c: float | None


def _score_mechanical(
    session: Session,
    user_id: int,
    rows: list[PredictionRecord],
    actuals: dict[date, "DayWeatherLike"],
    provenance: str,
) -> dict:
    """对冻结到期行落 OutcomeRecord + 评分。健身房不跑个人学习闭环
    （归因/规则统计是个人域语义，机械域样本混入会污染规则库）。"""
    from app.api.routes.predictions import _record_request, _score

    scored, skipped = [], []
    for row in rows:
        wdate = row.window_start.date()
        actual = actuals.get(wdate)
        judged = _judge_mechanical(row.event_type, row.success_criteria, actual) if actual else None
        if judged is None:
            skipped.append({"prediction_id": row.prediction_id, "reason": "实测数据缺失"})
            continue
        outcome_value, evidence = judged
        req = _record_request(
            session,
            row.prediction_id,
            user_reply=f"[{provenance}/机械] {evidence}",
            answered=True,
        )
        existing = session.exec(
            select(OutcomeRecord).where(OutcomeRecord.prediction_id == row.prediction_id)
        ).first()
        if existing is not None:
            skipped.append({"prediction_id": row.prediction_id, "reason": "已有 Outcome"})
            continue
        rec = OutcomeRecord(
            outcome_id=f"O-{row.prediction_id[-12:]}",
            prediction_id=row.prediction_id,
            request_id=req.request_id,
            outcome=outcome_value,
            confidence=1.0,
            evidence=evidence,
            needs_confirmation=False,
            disagreement=0.0,
        )
        session.add(rec)
        row.status = PredictionStatus.VERIFIED.value
        session.add(row)
        _score(session, row, outcome_value)
        scored.append(
            {"prediction_id": row.prediction_id, "outcome": outcome_value, "evidence": evidence}
        )
    session.commit()
    return {"status": "ok", "scored": scored, "skipped": skipped}


def _mature_rows(session: Session, user_id: int | None, as_of: date) -> list[PredictionRecord]:
    stmt = (
        select(PredictionRecord)
        .where(PredictionRecord.domain == Domain.WEATHER.value)
        .where(PredictionRecord.window_start < datetime.combine(as_of, time.min))
        .where(
            # RESEARCH 研究样本也在机械验证范围（研究期样本的意义就是喂校准）
            PredictionRecord.status.in_(
                [
                    PredictionStatus.FROZEN.value,
                    PredictionStatus.VERIFY_REQUIRED.value,
                    PredictionStatus.RESEARCH.value,
                ]
            )
        )
    )
    if user_id is not None:
        stmt = stmt.where(PredictionRecord.user_id == user_id)
    return list(session.exec(stmt).all())


# ----------------------------------------------------------------------
# 公开入口
# ----------------------------------------------------------------------
def seed_weather(
    session: Session,
    user_id: int,
    target: date | None = None,
    *,
    transport=None,
) -> dict:
    """冻结目标日（默认明天）的天气候选。已存在的 (日期, 事件) 幂等跳过。"""
    s = get_settings()
    target = target or (date.today() + timedelta(days=1))
    if _existing_event_types(session, user_id, target):
        return {"status": "already_seeded", "target": target.isoformat(), "frozen": []}
    provider = _provider(transport)
    try:
        stats = provider.climatology(target)
    except WeatherProviderError as exc:
        return {"status": "provider_error", "reason": str(exc), "frozen": []}
    specs = build_candidates(target, stats, s.XUANMIRROR_WEATHER_CITY)
    frozen = _freeze_candidates(
        session, user_id, target, specs, status=PredictionStatus.RESEARCH.value, provenance="live"
    )
    return {
        "status": "ok",
        "target": target.isoformat(),
        "candidates": [sp.description for sp in specs],
        "frozen": frozen,
    }


def preview_weather(target: date | None = None, *, transport=None) -> dict:
    """展示候选与 Null 概率，不落库。"""
    s = get_settings()
    target = target or (date.today() + timedelta(days=1))
    try:
        stats = _provider(transport).climatology(target)
    except WeatherProviderError as exc:
        return {"status": "provider_error", "reason": str(exc)}
    specs = build_candidates(target, stats, s.XUANMIRROR_WEATHER_CITY)
    return {
        "status": "ok",
        "target": target.isoformat(),
        "city": s.XUANMIRROR_WEATHER_CITY,
        "candidates": [
            {
                "event_type": sp.event_type,
                "description": sp.description,
                "null_probability": sp.probability,
                "success_criteria": sp.success_criteria,
            }
            for sp in specs
        ],
    }


def verify_due_weather(
    session: Session,
    user_id: int | None = None,
    *,
    as_of: date | None = None,
    transport=None,
) -> dict:
    """对所有到期天气预测做机械验证。window 早于 as_of 即视为可验。"""
    as_of = as_of or date.today()
    rows = _mature_rows(session, user_id, as_of)
    if not rows:
        return {"status": "ok", "scored": [], "skipped": []}
    w_start = min(r.window_start.date() for r in rows)
    w_end = max(r.window_start.date() for r in rows)
    try:
        actuals_list = _provider(transport).actual_daily(w_start, w_end)
    except WeatherProviderError as exc:
        return {"status": "provider_error", "reason": str(exc)}
    actuals = {dw.day: dw for dw in actuals_list}
    return _score_mechanical(session, user_id, rows, actuals, provenance="live")


def backfill_weather(
    session: Session,
    user_id: int,
    start: date,
    end: date,
    *,
    stride_days: int = 3,
    transport=None,
) -> dict:
    """历史回填：冻结过去日期的候选（provenance=backfill）并立即机械判定。

    纪律：end 不得 ≥ 今天（未来不可回填）；候选与 live 完全同构
    （同气候基线、同阈值、同冻结哈希链），区别只在溯源标与判定时点。
    回填样本只作校准种子与引擎体检，不得混入 live 技能统计（C-006）。
    """
    today = date.today()
    if end >= today:
        return {"status": "refused", "reason": "回填区间必须完全早于今天（防未来回填）"}
    if start > end:
        return {"status": "refused", "reason": "日期区间非法"}
    provider = _provider(transport)
    try:
        actuals = {dw.day: dw for dw in provider.actual_daily(start, end)}
    except WeatherProviderError as exc:
        return {"status": "provider_error", "reason": str(exc)}

    s = get_settings()
    frozen_all: list[str] = []
    results = []
    d = start
    while d <= end:
        # 幂等：该日已有天气预测（此前种子/回填过）整日跳过，防重复行
        if _existing_event_types(session, user_id, d):
            d += timedelta(days=stride_days)
            continue
        specs: list[WeatherCandidateSpec] = []
        try:
            stats = provider.climatology(d)
            specs = build_candidates(d, stats, s.XUANMIRROR_WEATHER_CITY)
        except WeatherProviderError as exc:
            results.append({"date": d.isoformat(), "error": str(exc)})
        if specs:
            frozen = _freeze_candidates(
                session, user_id, d, specs,
                status=PredictionStatus.RESEARCH.value, provenance="backfill",
            )
            frozen_all.extend(frozen)
        d += timedelta(days=stride_days)

    rows = [
        r
        for r in session.exec(
            select(PredictionRecord).where(
                PredictionRecord.user_id == user_id,
                PredictionRecord.domain == Domain.WEATHER.value,
            )
        ).all()
        if r.prediction_id in set(frozen_all)
    ]
    scored = _score_mechanical(session, user_id, rows, actuals, provenance="backfill")
    return {
        "status": "ok",
        "range": [start.isoformat(), end.isoformat()],
        "frozen": frozen_all,
        **scored,
    }
