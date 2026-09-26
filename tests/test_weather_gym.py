"""round 28：天气校准健身房（阴性对照域）测试。

全部走 httpx.MockTransport 合成数据，零真实网络。
"""

from __future__ import annotations

import httpx
import pytest
from sqlmodel import Session, SQLModel, create_engine, select
from sqlalchemy.pool import StaticPool
from datetime import date, datetime, timedelta

from app.models.core import User
from app.models.prediction import PredictionRecord
from app.models.scoring import OutcomeRecord, PredictionScore
from app.services import weather_gym


# ----------------------------------------------------------------------
# 合成 Open-Meteo 数据：确定性，可从同一函数反推期望值
# ----------------------------------------------------------------------
def _tmax(d: date) -> float:
    """0~29 均匀循环 → 分位数可解析预期。"""
    return float(d.timetuple().tm_yday % 30) + 10.0


def _precip(d: date) -> float:
    """每旬前 3 天有雨 → P(>=0.1mm) = 0.3。"""
    return 1.0 if (d.timetuple().tm_yday % 10) < 3 else 0.0


def _make_transport() -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        params = dict(request.url.params)
        url = str(request.url)
        if "archive-api" in url:
            start = date.fromisoformat(params["start_date"])
            end = date.fromisoformat(params["end_date"])
        else:
            today = date.today()
            past = int(params.get("past_days", 1))
            fc = int(params.get("forecast_days", 7))
            start = today - timedelta(days=past)
            end = today + timedelta(days=fc - 1)
        days = []
        d = start
        while d <= end:
            days.append(d)
            d += timedelta(days=1)
        return httpx.Response(
            200,
            json={
                "daily": {
                    "time": [d.isoformat() for d in days],
                    "temperature_2m_max": [_tmax(d) for d in days],
                    "temperature_2m_min": [5.0 for _ in days],
                    "precipitation_sum": [_precip(d) for d in days],
                    "weather_code": [0 for _ in days],
                }
            },
        )

    return httpx.MockTransport(handler)


@pytest.fixture()
def gym_db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        user = User(user_key="gym-user", display_name="健身房用户")
        session.add(user)
        session.commit()
        session.refresh(user)
        yield session, user.id
    engine.dispose()


@pytest.fixture(autouse=True)
def _mock_provider(monkeypatch):
    """weather_gym 的 provider 全部注入合成 transport，隔离真实网络。"""
    monkeypatch.setattr(
        weather_gym,
        "_provider",
        lambda transport=None: weather_gym.OpenMeteoProvider(
            22.82, 108.32, transport=_make_transport()
        ),
    )


def _expected_window_stats(target: date) -> tuple[int, float]:
    """与 provider 同口径的窗口统计（跨年按月日序）。"""
    lo, hi = target - timedelta(days=7), target + timedelta(days=7)
    lo_k, hi_k = (lo.month, lo.day), (hi.month, hi.day)
    wraps = lo_k > hi_k
    days, d = [], date(2015, 1, 1)
    end = date(2024, 12, 31)
    while d <= end:
        mk = (d.month, d.day)
        if (mk >= lo_k or mk <= hi_k) if wraps else (lo_k <= mk <= hi_k):
            days.append(d)
        d += timedelta(days=1)
    precip = sum(1 for d in days if _precip(d) >= 0.1) / len(days)
    return len(days), precip


# ----------------------------------------------------------------------
# Provider / 候选构建
# ----------------------------------------------------------------------
def test_climatology_matches_independent_recomputation(gym_db):
    p = weather_gym._provider()
    target = date(2026, 9, 26)
    stats = p.climatology(target)
    n, precip = _expected_window_stats(target)
    assert stats.sample_days == n
    assert stats.precip_ge_threshold_prob == pytest.approx(precip)
    # tmax = yday%30 + 10，窗口内均匀 → 中位数应落在 10~39 区间的中段附近
    assert 10.0 <= stats.tmax_quantiles[0.5] <= 39.0


def test_build_candidates_pre_registered(gym_db):
    p = weather_gym._provider()
    target = date(2026, 9, 26)
    specs = weather_gym.build_candidates(target, p.climatology(target), "南宁")
    types = {s.event_type for s in specs}
    assert types == {weather_gym.WEATHER_EVENT_PRECIP, weather_gym.WEATHER_EVENT_TEMP_HIGH}
    for sp in specs:
        assert 0.0 <= sp.probability <= 1.0
        assert weather_gym.NULL_RANGE[0] <= sp.probability <= weather_gym.NULL_RANGE[1]
        assert sp.success_criteria and sp.failure_criteria
        assert "≥" in sp.description  # 阈值必须显式进描述（可证伪）


def test_build_candidates_excludes_out_of_range_null(gym_db):
    """Null 概率超出 [0.15, 0.85] 的事件必须弃选（预注册纪律）。"""

    class _Stats:
        sample_days = 150
        precip_ge_threshold_prob = 0.95  # 超上限
        tmax_quantiles = {0.5: 30.0}

    specs = weather_gym.build_candidates(date(2026, 7, 1), _Stats(), "南宁")  # type: ignore[arg-type]
    assert weather_gym.WEATHER_EVENT_PRECIP not in {s.event_type for s in specs}
    assert weather_gym.WEATHER_EVENT_TEMP_HIGH in {s.event_type for s in specs}


# ----------------------------------------------------------------------
# 冻结 / 机械验证 / 回填
# ----------------------------------------------------------------------
def test_seed_freeze_and_dedup(gym_db):
    session, uid = gym_db
    past = date.today() - timedelta(days=10)
    result = weather_gym.seed_weather(session, uid, past)
    assert result["status"] == "ok"
    assert len(result["frozen"]) == 2
    rows = session.exec(
        select(PredictionRecord).where(PredictionRecord.user_id == uid)
    ).all()
    assert len(rows) == 2
    for r in rows:
        assert r.domain == "weather"
        assert r.status == "RESEARCH"
        assert r.provenance == "live"
        assert r.null_probability is not None
    # 幂等：同日二次种子跳过
    again = weather_gym.seed_weather(session, uid, past)
    assert again["status"] == "already_seeded"


def test_verify_due_mechanical_scoring(gym_db):
    session, uid = gym_db
    past = date.today() - timedelta(days=10)
    seed = weather_gym.seed_weather(session, uid, past)
    assert seed["status"] == "ok"

    result = weather_gym.verify_due_weather(session, uid)
    assert result["status"] == "ok"
    assert len(result["scored"]) == 2
    for s in result["scored"]:
        assert s["outcome"] in (0.0, 1.0)
        assert "机械判定" in s["evidence"]

    rows = session.exec(
        select(PredictionRecord).where(PredictionRecord.user_id == uid)
    ).all()
    for r in rows:
        assert r.status == "VERIFIED"
        outcome = session.exec(
            select(OutcomeRecord).where(OutcomeRecord.prediction_id == r.prediction_id)
        ).first()
        assert outcome is not None and outcome.confidence == 1.0
        actual = outcome.outcome
        # 机械判定必须与实测一致
        d = r.window_start.date()
        if r.event_type == weather_gym.WEATHER_EVENT_PRECIP:
            assert actual == (1.0 if _precip(d) >= 0.1 else 0.0)
        else:
            threshold = float(
                r.success_criteria[0].split("≥")[1].replace("°C", "")
            )
            assert actual == (1.0 if _tmax(d) >= threshold else 0.0)
        score = session.exec(
            select(PredictionScore).where(
                PredictionScore.prediction_id == r.prediction_id
            )
        ).first()
        assert score is not None
    # 已验证的不再重复判定
    rerun = weather_gym.verify_due_weather(session, uid)
    assert rerun["scored"] == []


def test_backfill_refuses_future_and_tags_provenance(gym_db):
    session, uid = gym_db
    today = date.today()
    refused = weather_gym.backfill_weather(
        session, uid, today - timedelta(days=5), today
    )
    assert refused["status"] == "refused"

    result = weather_gym.backfill_weather(
        session, uid, today - timedelta(days=9), today - timedelta(days=3), stride_days=3
    )
    assert result["status"] == "ok"
    assert len(result["frozen"]) >= 2
    rows = session.exec(
        select(PredictionRecord).where(PredictionRecord.user_id == uid)
    ).all()
    assert rows and all(r.provenance == "backfill" for r in rows)
    # 回填即判：所有回填行直接带 Outcome
    for r in rows:
        outcome = session.exec(
            select(OutcomeRecord).where(OutcomeRecord.prediction_id == r.prediction_id)
        ).first()
        assert outcome is not None

    # 幂等：同区间重复回填不得产生重复行（round 28 自审修复）
    n_before = len(rows)
    again = weather_gym.backfill_weather(
        session, uid, today - timedelta(days=9), today - timedelta(days=3), stride_days=3
    )
    assert again["status"] == "ok" and again["frozen"] == []
    rows2 = session.exec(
        select(PredictionRecord).where(PredictionRecord.user_id == uid)
    ).all()
    assert len(rows2) == n_before


def test_weather_excluded_from_manual_inbox(gym_db):
    """天气域不走人工验证收件箱（防主观判定污染阴性对照）。"""
    session, uid = gym_db
    past = date.today() - timedelta(days=10)
    weather_gym.seed_weather(session, uid, past)
    # 种子的是过去日期，window 早于 now：若不过滤必然出现在 due 收件箱
    from fastapi.testclient import TestClient

    from app.database import get_session
    from app.main import app

    engine = session.get_bind()

    def _override():
        yield session

    app.dependency_overrides[get_session] = _override
    try:
        with TestClient(app) as c:
            resp = c.get(f"/api/predictions/due?user_id={uid}")
            assert resp.status_code == 200
            items = resp.json()["items"]
            assert all(it["domain"] != "weather" for it in items)
    finally:
        app.dependency_overrides.pop(get_session, None)


def test_missing_actual_is_skipped_not_fabricated(gym_db, monkeypatch):
    """实测缺失时诚实跳过，不得编造结果（C-006）。"""
    session, uid = gym_db
    past = date.today() - timedelta(days=10)
    weather_gym.seed_weather(session, uid, past)

    def _empty_actual(self, start, end):
        return []

    monkeypatch.setattr(
        weather_gym.OpenMeteoProvider, "actual_daily", _empty_actual
    )
    result = weather_gym.verify_due_weather(session, uid)
    assert result["scored"] == []
    assert len(result["skipped"]) == 2
