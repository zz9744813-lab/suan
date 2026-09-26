"""Open-Meteo 天气数据源 —— 校准健身房（阴性对照域）的外部事实层。

对应 C-007「现实优先」与第 78 节小样本保护：
天气域的真值由外部 API 给出，判定零人工裁量，是概率机器（Brier / 校准 bins /
可靠度矩阵）最快的喂料通道，同时充当术式信号的阴性对照——
术式在这个纯物理域上"跑赢"Null 更可能是代码泄漏而非奇迹。

选型：Open-Meteo（github.com/open-meteo/open-meteo，AGPL）。
    - 完全免费、无 API key、无注册；
    - forecast 端点含 recent actuals（past_days），archive 端点（ERA5）覆盖 1940 起；
    - 本机代理陷阱（HANDOFF 坑 4.3）：必须 trust_env=False，绝不走系统代理。

历史气候基线（climatology）= Null Model 的天气版：用 archive 多年同期
±窗口日统计「降水概率 / 气温分位数」，进程内缓存一次全量拉取。
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import date, timedelta

import httpx

logger = logging.getLogger("xuanmirror.weather")

_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
_ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"

# ERA5 archive 有约 5 天滞后；最近几天用 forecast 的 past_days 实况补齐
_ARCHIVE_LAG_DAYS = 7
# climatology 统计窗：目标日期 ±7 天 × 2015-2024 十年
_CLIMO_YEARS = (2015, 2024)
_CLIMO_WINDOW_DAYS = 7


class WeatherProviderError(RuntimeError):
    """天气数据源不可用。调用方必须诚实降级，不得编造数据。"""


@dataclass(frozen=True)
class DayWeather:
    day: date
    precipitation_mm: float | None = None
    tmax_c: float | None = None
    tmin_c: float | None = None


@dataclass(frozen=True)
class ClimoStats:
    """目标日期 ±7 天窗口的多年气候统计。"""

    sample_days: int
    precip_ge_threshold_prob: float  # P(日降水量 >= 0.1mm)
    tmax_quantiles: dict[float, float]  # 分位数 -> °C（0.1/0.25/0.5/0.75/0.9）


def _quantile(sorted_vals: list[float], q: float) -> float:
    """线性插值分位数（与 numpy 默认 linear 策略一致）。"""
    if not sorted_vals:
        raise WeatherProviderError("空样本无法计算分位数")
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    pos = q * (len(sorted_vals) - 1)
    lo = int(pos)
    hi = min(lo + 1, len(sorted_vals) - 1)
    frac = pos - lo
    return sorted_vals[lo] * (1 - frac) + sorted_vals[hi] * frac


class OpenMeteoProvider:
    """Open-Meteo 客户端。transport 参数仅供测试注入 httpx.MockTransport。"""

    def __init__(
        self,
        lat: float,
        lon: float,
        *,
        timeout: float = 20.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.lat = lat
        self.lon = lon
        # 坑 4.3：全局代理 127.0.0.1:2080 会挂死外网请求，必须显式绕过
        self._client = httpx.Client(
            trust_env=False, timeout=timeout, transport=transport
        )
        self._climo_cache: dict[tuple[int, int], ClimoStats] | None = None
        self._climo_raw: list[DayWeather] | None = None

    # ------------------------------------------------------------------
    # 原始拉取
    # ------------------------------------------------------------------
    def _fetch_daily(self, url: str, params: dict) -> list[DayWeather]:
        for attempt in (1, 2):
            try:
                resp = self._client.get(url, params=params)
                resp.raise_for_status()
                break
            except httpx.HTTPError as exc:
                if attempt == 2:
                    raise WeatherProviderError(f"Open-Meteo 请求失败：{exc}") from exc
                time.sleep(1.0)
        try:
            daily = resp.json()["daily"]
            days = [date.fromisoformat(d) for d in daily["time"]]
        except (KeyError, ValueError, TypeError) as exc:
            raise WeatherProviderError(f"Open-Meteo 响应结构异常：{exc}") from exc

        def _num(key: str, i: int) -> float | None:
            v = (daily.get(key) or [None] * len(days))[i]
            return float(v) if v is not None else None

        return [
            DayWeather(
                day=d,
                precipitation_mm=_num("precipitation_sum", i),
                tmax_c=_num("temperature_2m_max", i),
                tmin_c=_num("temperature_2m_min", i),
            )
            for i, d in enumerate(days)
        ]

    # ------------------------------------------------------------------
    # 实况（验证用）
    # ------------------------------------------------------------------
    def actual_daily(self, start: date, end: date) -> list[DayWeather]:
        """已发生日期的逐日实况。近几天走 forecast past_days，更早走 archive。"""
        if start > end:
            raise WeatherProviderError("日期区间非法：start > end")
        today = date.today()
        if end >= today - timedelta(days=_ARCHIVE_LAG_DAYS):
            past_days = max(1, (today - start).days + 1)
            return self._fetch_daily(
                _FORECAST_URL,
                {
                    "latitude": self.lat,
                    "longitude": self.lon,
                    "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_sum",
                    "timezone": "Asia/Shanghai",
                    "past_days": min(past_days, 92),
                    "forecast_days": 1,
                },
            )
        return self._fetch_daily(
            _ARCHIVE_URL,
            {
                "latitude": self.lat,
                "longitude": self.lon,
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
                "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum",
                "timezone": "Asia/Shanghai",
            },
        )

    # ------------------------------------------------------------------
    # 气候基线（Null）
    # ------------------------------------------------------------------
    def _climo_daily(self) -> list[DayWeather]:
        """十年全量日值，一次拉取进程内复用。"""
        if self._climo_raw is None:
            self._climo_raw = self._fetch_daily(
                _ARCHIVE_URL,
                {
                    "latitude": self.lat,
                    "longitude": self.lon,
                    "start_date": f"{_CLIMO_YEARS[0]}-01-01",
                    "end_date": f"{_CLIMO_YEARS[1]}-12-31",
                    "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum",
                    "timezone": "Asia/Shanghai",
                },
            )
            logger.info(
                "climatology 载入：%d 天（%d-%d）",
                len(self._climo_raw), *_CLIMO_YEARS,
            )
        return self._climo_raw

    def climatology(
        self, target: date, *, precip_threshold_mm: float = 0.1
    ) -> ClimoStats:
        """目标日期 ±7 天窗口的多年统计（结果按 (月, 日) 缓存）。"""
        key = (target.month, target.day)
        if self._climo_cache is None:
            self._climo_cache = {}
        if key not in self._climo_cache:
            lo = target - timedelta(days=_CLIMO_WINDOW_DAYS)
            hi = target + timedelta(days=_CLIMO_WINDOW_DAYS)
            lo_key, hi_key = (lo.month, lo.day), (hi.month, hi.day)
            wraps_year = lo_key > hi_key  # 1 月初 / 12 月底的 ±7 天窗跨年

            def _in_window(dw: DayWeather) -> bool:
                mk = (dw.day.month, dw.day.day)
                return mk >= lo_key or mk <= hi_key if wraps_year else lo_key <= mk <= hi_key

            rows = [dw for dw in self._climo_daily() if _in_window(dw)]
            precip_known = [
                dw.precipitation_mm for dw in rows if dw.precipitation_mm is not None
            ]
            tmax_known = [dw.tmax_c for dw in rows if dw.tmax_c is not None]
            if len(precip_known) < 50 or len(tmax_known) < 50:
                raise WeatherProviderError(
                    f"climatology 样本不足（降水 {len(precip_known)} / 气温 {len(tmax_known)}）"
                )
            tmax_sorted = sorted(tmax_known)
            self._climo_cache[key] = ClimoStats(
                sample_days=len(rows),
                precip_ge_threshold_prob=sum(
                    1 for v in precip_known if v >= precip_threshold_mm
                )
                / len(precip_known),
                tmax_quantiles={
                    q: round(_quantile(tmax_sorted, q), 1)
                    for q in (0.1, 0.25, 0.5, 0.75, 0.9)
                },
            )
        return self._climo_cache[key]

    def close(self) -> None:
        self._client.close()
