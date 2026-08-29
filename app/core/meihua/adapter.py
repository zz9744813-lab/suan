"""MeihuaAdapter —— 梅花易数信号。

对应工程方案：
- 第 6.1 节 梅花易数（时间起卦 / 数字起卦 / 本卦互卦变卦 / 体用 / 五行）
- 第 14 节 统一 Signal Schema
- 第 53 节 Adapter 策略

C-006：梅花作为 Traditional Metaphysical Signal 进入系统。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlmodel import Session, select

from app.core.base import AdapterQuery, MetaphysicalAdapter, registry
from app.models.core import BirthProfile
from app.schemas.signal import (
    Domain,
    Evidence,
    EvidenceSource,
    Signal,
    SourceType,
)

from .engine import ENGINE_VERSION, cast_hexagram

# 体用关系 → 传统吉凶（direction）
RELATION_DIRECTION = {
    "用生体": 1.0,
    "体克用": 1.0,
    "比和": 0.0,
    "体生用": -1.0,
    "用克体": -1.0,
}

# 用生体/体克用等吉象在不同领域的强度（弱先验）
RELATION_STRENGTH = {
    "用生体": 0.7,
    "体克用": 0.6,
    "比和": 0.4,
    "体生用": 0.55,
    "用克体": 0.65,
}


class MeihuaAdapter(MetaphysicalAdapter):
    source = SourceType.MEIHUA
    engine_name = "meihua-engine"
    engine_version = ENGINE_VERSION

    @property
    def available(self) -> bool:
        return True  # 纯 Python 自研

    # ------------------------------------------------------------------
    def compute_chart(self, query: AdapterQuery) -> dict[str, Any]:
        """确定性起卦（第 54 节）。"""
        profile = None
        if query.session is not None:
            profile = query.session.exec(
                select(BirthProfile).where(BirthProfile.user_id == query.user_id)
            ).first()

        dt = datetime.combine(query.target_date, datetime.min.time())
        try:
            h, m = (query.target_time or "00:00").split(":")
            dt = dt.replace(hour=int(h), minute=int(m))
        except (ValueError, AttributeError):
            pass

        from app.core.calendar.core import CalendarCore

        core = CalendarCore()
        cal = core.compute(
            birth_date=(profile.solar_birth_date if profile else dt.date()),
            birth_time=f"{dt.hour:02d}:{dt.minute:02d}",
            target_date=dt.date(), target_time=f"{dt.hour:02d}:{dt.minute:02d}",
            gender="unknown",
        )
        if cal.degraded:
            year_branch = "子"  # 兜底（不应发生，CalendarCore 通常可用）
        else:
            ygz = str(cal.payload.get("year_ganzhi", ""))
            year_branch = ygz[1] if len(ygz) > 1 else "子"

        hour_branch = "子丑寅卯辰巳午未申酉戌亥"[((dt.hour + 1) // 2) % 12]
        return cast_hexagram(dt, year_branch=year_branch, hour_branch=hour_branch)

    # ------------------------------------------------------------------
    def to_signals(self, query: AdapterQuery, chart: dict[str, Any]) -> list[Signal]:
        """本卦/互卦/变卦 + 体用 → Signal。

        规则（骨架，待验证）：
            体用五行生克关系决定方向（第 6.1 节传统用法）。
        """
        relation = chart.get("relation", "比和")
        direction = RELATION_DIRECTION.get(relation, 0.0)
        strength = RELATION_STRENGTH.get(relation, 0.4)

        rule_id = f"MEIHUA-R-{relation}-{query.domain.value}"

        return [
            Signal(
                **self._base_signal_kwargs(query),
                direction=direction,
                strength=strength,
                confidence=0.32,  # 弱先验（禁止 6）
                evidence=[
                    Evidence(
                        source=EvidenceSource.TRADITIONAL_RULE,
                        rule_id=rule_id,
                        description=(
                            f"本卦{chart['ben_gua']['name']}，互卦{chart['hu_gua']['name']}，"
                            f"变卦{chart['bian_gua']['name']}，"
                            f"动爻第{chart['moving_yao']}爻"
                        ),
                    ),
                    Evidence(
                        source=EvidenceSource.TRADITIONAL_RULE,
                        rule_id=rule_id,
                        description=(
                            f"体卦{chart['ti_gua']}（{chart['ti_wuxing']}）"
                            f"对用卦{chart['yong_gua']}（{chart['yong_wuxing']}）：{relation}"
                        ),
                    ),
                ],
                counter_evidence=(
                    [
                        Evidence(
                            source=EvidenceSource.TRADITIONAL_RULE,
                            rule_id=rule_id,
                            description=f"{relation} 对 {query.domain.value} 传统上非吉",
                        )
                    ]
                    if direction < 0
                    else []
                ),
                rule_ids=[rule_id],
                dependency_group="yi_jing",  # 第 20.12 节：与六爻同属易卦体系
            )
        ]


registry.register(MeihuaAdapter())
