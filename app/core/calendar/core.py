"""Calendar Core —— 全系统唯一的历法内核。

对应工程方案第 6.1 节：

    所有术式必须共享同一个 Calendar Core。
    禁止每个模块自己算日期。

统一负责：
    公历 / 农历 / 节气 / 干支 / 四柱 / 五行 / 十神 / 大运 / 流年 / 流月 / 流日

第 54 节硬性约束：
    输入完全相同 → 输出必须完全相同（golden case 可复现）。
    因此所有计算必须 deterministic，禁止引入随机数或「当前时间」。

依赖 lunar-python（可选）。缺失时进入 DEGRADED 模式：
    返回 degraded=True 的快照，对应 Signal 必须跳过而非当作 0。
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime

from app.utils import utcnow
from typing import Any

from sqlmodel import Session

from app.models.core import BirthProfile, CalendarSnapshot

ENGINE_VERSION = "calendar-0.1.0"

TIANGAN = "甲乙丙丁戊己庚辛壬癸"
DIZHI = "子丑寅卯辰巳午未申酉戌亥"

# 五行（按天干顺序）
TIANGAN_WUXING = "木木火火土土金金水水"
DIZHI_WUXING = "水土木木土火火土金金水"


@dataclass
class CalendarResult:
    """Calendar Core 的结构化输出。"""

    payload: dict[str, Any]
    degraded: bool = False
    degrade_reason: str | None = None

    @property
    def year_ganzhi(self) -> str:
        return str(self.payload.get("year_ganzhi", ""))


class CalendarCore:
    """统一的历法计算内核。

    所有术式 Adapter 必须从这里取值，禁止各自实现日期/干支逻辑。
    """

    def __init__(self) -> None:
        self._lunar_module: Any = None
        self._available: bool | None = None

    # ------------------------------------------------------------------
    # 引擎可用性
    # ------------------------------------------------------------------
    @property
    def available(self) -> bool:
        if self._available is None:
            try:
                from lunar_python import Solar  # noqa: F401

                self._lunar_module = True
                self._available = True
            except ImportError:
                self._available = False
        return self._available

    def _degraded(self, reason: str) -> CalendarResult:
        # 第 6 节：引擎缺失时不得静默给出错误结果
        return CalendarResult(payload={}, degraded=True, degrade_reason=reason)

    # ------------------------------------------------------------------
    # 输入哈希（第 54 节 golden case 锚点）
    # ------------------------------------------------------------------
    @staticmethod
    def compute_input_hash(
        *,
        birth_date: date,
        birth_time: str,
        target_date: date,
        target_time: str,
        gender: str,
        use_true_solar_time: bool,
        longitude: float | None,
    ) -> str:
        raw = json.dumps(
            {
                "birth_date": birth_date.isoformat(),
                "birth_time": birth_time,
                "target_date": target_date.isoformat(),
                "target_time": target_time,
                "gender": gender,
                "use_true_solar_time": use_true_solar_time,
                "longitude": longitude,
                "engine": ENGINE_VERSION,
            },
            sort_keys=True,
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    # ------------------------------------------------------------------
    # 主计算
    # ------------------------------------------------------------------
    def compute(
        self,
        *,
        birth_date: date,
        birth_time: str = "00:00",
        target_date: date | None = None,
        target_time: str = "00:00",
        gender: str = "unknown",
        use_true_solar_time: bool = True,
        longitude: float | None = None,
    ) -> CalendarResult:
        """计算指定时刻的完整历法快照。

        deterministic：相同输入永远返回相同结果。
        """
        if target_date is None:
            target_date = utcnow().date()

        if not self.available:
            return self._degraded("lunar-python 未安装，请 pip install lunar-python")

        try:
            return self._compute_with_lunar(
                birth_date=birth_date,
                birth_time=birth_time,
                target_date=target_date,
                target_time=target_time,
                gender=gender,
                use_true_solar_time=use_true_solar_time,
                longitude=longitude,
            )
        except Exception as exc:  # pragma: no cover - 引擎异常不应击穿调用方
            return self._degraded(f"lunar-python 计算异常：{exc}")

    # ------------------------------------------------------------------
    def _compute_with_lunar(
        self,
        *,
        birth_date: date,
        birth_time: str,
        target_date: date,
        target_time: str,
        gender: str,
        use_true_solar_time: bool,
        longitude: float | None,
    ) -> CalendarResult:
        from lunar_python import Solar

        # ---------- 目标时刻：四柱 ----------
        t_h, t_m = self._parse_time(target_time)
        target_solar = Solar.fromYmdHms(
            target_date.year, target_date.month, target_date.day, t_h, t_m, 0
        )
        target_lunar = target_solar.getLunar()

        year_gz = target_lunar.getYearInGanZhi()
        month_gz = target_lunar.getMonthInGanZhi()
        day_gz = target_lunar.getDayInGanZhi()
        hour_gz = target_lunar.getTimeInGanZhi()

        payload: dict[str, Any] = {
            "year_ganzhi": year_gz,
            "month_ganzhi": month_gz,
            "day_ganzhi": day_gz,
            "hour_ganzhi": hour_gz,
        }

        # ---------- 农历 ----------
        payload.update(
            {
                "lunar_year": target_lunar.getYear(),
                "lunar_month": abs(target_lunar.getMonth()),
                "lunar_day": target_lunar.getDay(),
                "is_leap_month": target_lunar.getMonth() < 0,
            }
        )

        # ---------- 节气 ----------
        try:
            jq = target_lunar.getCurrentJieQi()
            payload["current_jieqi"] = jq.getName() if jq else ""
            payload["jieqi_date"] = (
                jq.getSolar().toYmd() if jq and jq.getSolar() else None
            )
        except Exception:
            payload["current_jieqi"] = ""
            payload["jieqi_date"] = None

        # ---------- 五行 ----------
        payload["wuxing"] = {
            "year": self._gz_wuxing(year_gz),
            "month": self._gz_wuxing(month_gz),
            "day": self._gz_wuxing(day_gz),
            "hour": self._gz_wuxing(hour_gz),
        }

        # ---------- 本命八字：四柱 / 十神 / 大运 ----------
        b_h, b_m = self._parse_time(birth_time)
        birth_solar = Solar.fromYmdHms(
            birth_date.year, birth_date.month, birth_date.day, b_h, b_m, 0
        )
        birth_lunar = birth_solar.getLunar()

        try:
            ec = birth_lunar.getEightChar()
            # 第 6 节：阳历/农历排盘方式差异，默认用「按节气」的正规八字
            ec.setSect(2)  # 2 = 按节气（新派），1 = 按农历（旧派）

            payload["bazi"] = {
                "year": ec.getYear(),
                "month": ec.getMonth(),
                "day": ec.getDay(),
                "time": ec.getTime(),
                # 日主 = 日柱天干
                "day_master": ec.getDayGan(),
            }
            # 十神分天干/地支两套（lunar-python API：...ShiShenGan / ...ShiShenZhi）
            payload["shishen"] = {
                "year": ec.getYearShiShenGan(),
                "month": ec.getMonthShiShenGan(),
                "day": ec.getDayShiShenGan(),
                "time": ec.getTimeShiShenGan(),
            }
            payload["shishen_zhi"] = {
                "year": ec.getYearShiShenZhi(),
                "month": ec.getMonthShiShenZhi(),
                "day": ec.getDayShiShenZhi(),
                "time": ec.getTimeShiShenZhi(),
            }
            # 四柱五行 / 纳音 / 命宫（第 6 节：统一由 Calendar Core 提供）
            payload["bazi_wuxing"] = {
                "year": ec.getYearWuXing(),
                "month": ec.getMonthWuXing(),
                "day": ec.getDayWuXing(),
                "time": ec.getTimeWuXing(),
            }
            payload["nayin"] = {
                "year": ec.getYearNaYin(),
                "month": ec.getMonthNaYin(),
                "day": ec.getDayNaYin(),
                "time": ec.getTimeNaYin(),
            }
            payload["ming_gong"] = ec.getMingGong()

            # ---------- 大运 ----------
            gender_code = 1 if gender == "male" else (0 if gender == "female" else 1)
            yun = ec.getYun(gender_code)
            payload["dayun"] = [
                {
                    "start_age": dy.getStartAge(),
                    "start_year": dy.getStartYear(),
                    "ganzhi": dy.getGanZhi(),
                }
                for dy in (yun.getDaYun() or [])[:12]
            ]
        except Exception as exc:
            payload["bazi"] = {}
            payload["shishen"] = {}
            payload["dayun"] = []
            payload["bazi_error"] = str(exc)

        # ---------- 流年 / 流月 / 流日（相对目标时刻）----------
        payload["liunian"] = year_gz
        payload["liuyue"] = month_gz
        payload["liuri"] = day_gz

        if use_true_solar_time and longitude is not None:
            # 真太阳时校正：每偏离标准经度 1° 约 4 分钟
            payload["true_solar_correction_minutes"] = round((longitude - 120.0) * 4.0, 2)

        return CalendarResult(payload=payload)

    # ------------------------------------------------------------------
    @staticmethod
    def _parse_time(hhmm: str) -> tuple[int, int]:
        try:
            parts = (hhmm or "00:00").split(":")
            return int(parts[0]), int(parts[1]) if len(parts) > 1 else 0
        except (ValueError, AttributeError):
            return 0, 0

    @classmethod
    def _gz_wuxing(cls, ganzhi: str) -> str:
        """干支 → 五行（取天干五行 + 地支五行）。"""
        if not ganzhi or len(ganzhi) < 2:
            return ""
        tg, dz = ganzhi[0], ganzhi[1]
        out = []
        if tg in TIANGAN:
            out.append(TIANGAN_WUXING[TIANGAN.index(tg)])
        if dz in DIZHI:
            out.append(DIZHI_WUXING[DIZHI.index(dz)])
        return "".join(out)


# ----------------------------------------------------------------------
# 会话级封装
# ----------------------------------------------------------------------
def get_or_build_snapshot(
    session: Session,
    *,
    user_id: int,
    profile: BirthProfile,
    target_date: date,
    target_time: str = "00:00",
) -> CalendarSnapshot:
    """取缓存快照，未命中则计算并落库。

    第 54 节：快照以 input_hash 为键，保证同输入同输出。
    """
    input_hash = CalendarCore.compute_input_hash(
        birth_date=profile.solar_birth_date,
        birth_time=profile.solar_birth_time,
        target_date=target_date,
        target_time=target_time,
        gender=profile.gender,
        use_true_solar_time=profile.use_true_solar_time,
        longitude=profile.longitude,
    )

    from sqlmodel import select

    existing = session.exec(
        select(CalendarSnapshot).where(
            CalendarSnapshot.user_id == user_id,
            CalendarSnapshot.input_hash == input_hash,
        )
    ).first()
    if existing:
        return existing

    core = CalendarCore()
    result = core.compute(
        birth_date=profile.solar_birth_date,
        birth_time=profile.solar_birth_time,
        target_date=target_date,
        target_time=target_time,
        gender=profile.gender,
        use_true_solar_time=profile.use_true_solar_time,
        longitude=profile.longitude,
    )

    snapshot = CalendarSnapshot(
        user_id=user_id,
        target_date=target_date,
        target_time=target_time,
        input_hash=input_hash,
        payload=result.payload,
        engine_version=ENGINE_VERSION,
        year_ganzhi=str(result.payload.get("year_ganzhi", "")),
        month_ganzhi=str(result.payload.get("month_ganzhi", "")),
        day_ganzhi=str(result.payload.get("day_ganzhi", "")),
        hour_ganzhi=str(result.payload.get("hour_ganzhi", "")),
        lunar_year=result.payload.get("lunar_year"),
        lunar_month=result.payload.get("lunar_month"),
        lunar_day=result.payload.get("lunar_day"),
        is_leap_month=bool(result.payload.get("is_leap_month", False)),
        current_jieqi=str(result.payload.get("current_jieqi", "")),
        liunian_ganzhi=str(result.payload.get("liunian", "")),
        liuyue_ganzhi=str(result.payload.get("liuyue", "")),
        liuri_ganzhi=str(result.payload.get("liuri", "")),
    )
    session.add(snapshot)
    session.commit()
    session.refresh(snapshot)
    return snapshot
