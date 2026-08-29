"""BaziAdapter —— 八字信号（V0.1 主术式）。

对应工程方案：
- 第 6.1 节 八字 / 历法（lunar-python）
- 第 14 节 统一 Signal Schema
- 第 25 节 Rule Registry
- 第 53 节 Adapter 策略

C-006：八字作为 Traditional Metaphysical Signal 进入系统，
      其有效性必须由系统自己的长期验证结果决定，不得预先假定有效。

第 6.1 节硬性规则：
    程序负责排盘，LLM 不允许自己算命盘。
    所有术式必须共享同一个 Calendar Core。
"""

from __future__ import annotations

import hashlib
import json
from datetime import date
from typing import Any

from app.core.base import AdapterQuery, MetaphysicalAdapter, registry
from app.core.calendar.core import CalendarCore
from app.schemas.signal import (
    Domain,
    Evidence,
    EvidenceSource,
    Signal,
    SourceType,
)

ENGINE_VERSION = "bazi-0.1.0"

TIANGAN = "甲乙丙丁戊己庚辛壬癸"
# 五行：木木火火土土金金水水
TG_WUXING = ["木", "木", "火", "火", "土", "土", "金", "金", "水", "水"]

# 五行生克：key 生 value / key 克 value
WUXING_SHENG = {"木": "火", "火": "土", "土": "金", "金": "水", "水": "木"}
WUXING_KE = {"木": "土", "土": "水", "水": "火", "火": "金", "金": "木"}

# 十神定义：以日主为基准，同五行=比劫，生日主=印，日主生=食伤，
# 克日主=官杀，日主克=财
#  domain → 传统上认为「有利」的十神类别
DOMAIN_FAVORABLE_SHISHEN: dict[Domain, set[str]] = {
    Domain.CAREER: {"官", "印"},          # 官=职位压力/晋升，印=贵人/资质
    Domain.MONEY: {"财"},                  # 财星
    Domain.STUDY: {"印"},                  # 印=学习
    Domain.SOCIAL: {"比劫", "食伤"},        # 同辈、表达
    Domain.COMMUNICATION: {"食伤"},        # 食伤=表达输出
    Domain.PROJECT: {"财", "官"},
    Domain.UNEXPECTED_EVENT: {"官", "劫"},  # 官杀=突发压力
    Domain.SCHEDULE: {"官"},
}


def wuxing_of(tiangan: str) -> str:
    return TG_WUXING[TIANGAN.index(tiangan)] if tiangan in TIANGAN else ""


def shishen_category(day_master: str, other: str) -> str:
    """日主与其他天干的十神类别（简化版：仅按五行生克分类）。

    完整十神需区分阴阳（正/偏），骨架阶段用类别：
        比劫 / 印 / 食伤 / 官 / 财
    """
    dm_wx = wuxing_of(day_master)
    ot_wx = wuxing_of(other)
    if not dm_wx or not ot_wx:
        return ""
    if dm_wx == ot_wx:
        return "比劫"
    if WUXING_SHENG.get(ot_wx) == dm_wx:
        return "印"          # 他生我
    if WUXING_SHENG.get(dm_wx) == ot_wx:
        return "食伤"        # 我生他
    if WUXING_KE.get(ot_wx) == dm_wx:
        return "官"          # 他克我
    if WUXING_KE.get(dm_wx) == ot_wx:
        return "财"          # 我克他
    return ""


class BaziAdapter(MetaphysicalAdapter):
    source = SourceType.BAZI
    engine_name = "lunar-python"
    engine_version = ENGINE_VERSION

    def __init__(self) -> None:
        self._core = CalendarCore()

    @property
    def available(self) -> bool:
        return self._core.available

    # ------------------------------------------------------------------
    def compute_chart(self, query: AdapterQuery) -> dict[str, Any]:
        """确定性排盘。共享 CalendarCore（第 6.1 节禁止各自算日期）。

        需要用户提供 BirthProfile。session 由调用方注入（便于测试隔离），
        未注入时回退到全局 engine。
        """
        from sqlmodel import Session, select

        from app.database import engine as db_engine
        from app.models.core import BirthProfile

        stmt = select(BirthProfile).where(
            BirthProfile.user_id == query.user_id,
            BirthProfile.is_primary.is_(True),  # type: ignore[union-attr]
        )

        if query.session is not None:
            profile = query.session.exec(stmt).first()
        else:
            with Session(db_engine) as session:
                profile = session.exec(stmt).first()

        if profile is None:
            return {}

        result = self._core.compute(
            birth_date=profile.solar_birth_date,
            birth_time=profile.solar_birth_time,
            target_date=query.target_date,
            target_time=query.target_time,
            gender=profile.gender,
            use_true_solar_time=profile.use_true_solar_time,
            longitude=profile.longitude,
        )

        if result.degraded:
            return {}

        return {
            "input_hash": self.input_hash(
                "bazi",
                user_id=query.user_id,
                target_date=query.target_date,
                target_time=query.target_time,
            ),
            **result.payload,
            "birth_time_known": True,
        }

    # ------------------------------------------------------------------
    def to_signals(self, query: AdapterQuery, chart: dict[str, Any]) -> list[Signal]:
        """排盘 → Signal。

        骨架规则（待验证）：
            流日/流月天干相对日主的十神类别，与目标 domain 的有利十神做匹配，
            匹配则给出正向信号，相克则给出负向信号。

        C-006：这只是待验证信号，不代表已证实有效。
        """
        bazi = chart.get("bazi") or {}
        day_master = bazi.get("day_master", "")
        if not day_master:
            return []

        # 按时间尺度选取对照干支
        scale_to_ganzhi = {
            "day": chart.get("liuri", ""),
            "week": chart.get("liuyue", ""),
            "month": chart.get("liuyue", ""),
            "year": chart.get("liunian", ""),
        }
        ganzhi = scale_to_ganzhi.get(query.time_scale.value, chart.get("liuri", ""))
        if not ganzhi:
            return []

        tiangan = ganzhi[0]
        category = shishen_category(day_master, tiangan)
        if not category:
            return []

        favorable = DOMAIN_FAVORABLE_SHISHEN.get(query.domain, set())
        is_favorable = category in favorable

        # direction：有利为 +1，不利为 -1
        direction = 1.0 if is_favorable else -1.0

        # strength：十神类别与 domain 的相关度（骨架用固定档位）
        # 第 43 节：信息不足时必须降低信心 —— 出生时辰不确定会拉低 confidence
        strength = 0.6 if is_favorable else 0.4
        confidence = 0.35  # 单一十神规则，弱先验（禁止 6：初始只允许弱先验）

        rule_id = f"BAZI-R-{category}-{query.domain.value}"

        return [
            Signal(
                **self._base_signal_kwargs(query),
                direction=direction,
                strength=strength,
                confidence=confidence,
                evidence=[
                    Evidence(
                        source=EvidenceSource.CALENDAR,
                        rule_id=rule_id,
                        description=f"日主{day_master} 对 {ganzhi}（{query.time_scale.value}）→ {category}",
                    )
                ],
                counter_evidence=(
                    []
                    if is_favorable
                    else [
                        Evidence(
                            source=EvidenceSource.TRADITIONAL_RULE,
                            rule_id=rule_id,
                            description=f"{category} 对 {query.domain.value} 传统上非有利",
                        )
                    ]
                ),
                rule_ids=[rule_id],
                # 第 20.12 节：八字与紫微、黄历共享历法信号，不能当作独立证据
                dependency_group="lunar_calendar",
            )
        ]


# 注册到全局 Adapter 注册表（第 53 节）
registry.register(BaziAdapter())
