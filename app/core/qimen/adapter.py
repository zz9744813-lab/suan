"""QimenAdapter —— 奇门遁甲信号。

对应工程方案：
- 第 6.1 节 奇门遁甲（九宫/九星/八门/八神/阴阳遁/三元/节气/格局）
- 第 14 节 统一 Signal Schema
- 第 53 节 Adapter 策略
- V1 优先用于小时级、日级、具体事件

引擎：移植自 FANzR-arch/Numerologist_skills（确定性，lunar-python 历法）。
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

from .engine import cast_chart

ENGINE_VERSION = "qimen-0.1.0"

# 吉门 / 凶门（第 6.1 节传统用法）
JI_MEN = {"开", "休", "生"}
XIONG_MEN = {"死", "惊", "伤", "杜", "景"}

# 吉凶格局 → 方向
PATTERN_DIRECTION = {
    "三奇配吉门": 1.0,
    "值符得位": 0.8,
    "伏吟": -1.0,
    "反吟": -1.0,
    "门迫": -0.6,
}


class QimenAdapter(MetaphysicalAdapter):
    source = SourceType.QIMEN
    engine_name = "qimen-engine"
    engine_version = ENGINE_VERSION

    @property
    def available(self) -> bool:
        try:
            from lunar_python import Solar  # noqa: F401

            return True
        except ImportError:
            return False

    # ------------------------------------------------------------------
    def compute_chart(self, query: AdapterQuery) -> dict[str, Any]:
        """确定性排盘（第 54 节）。"""
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

        # 第 64 节：默认东八区（时区定义在 User 表，此处按系统默认处理）
        tz_name = "Asia/Shanghai"
        chart = cast_chart(dt, timezone_name=tz_name)
        if "error" in chart:
            return {}
        return chart

    # ------------------------------------------------------------------
    def to_signals(self, query: AdapterQuery, chart: dict[str, Any]) -> list[Signal]:
        """盘面 → Signal。

        规则（骨架，待验证）：
            1. 值符所在宫的门：吉门 → 正向，凶门 → 负向；
            2. 盘面格局（三奇配吉门/伏吟/反吟/门迫）叠加方向；
            3. 时干落宫与用神宫关系（简化版）。
        """
        signals: list[Signal] = []
        rule_ids: list[str] = []
        evidence: list[Evidence] = []
        counter: list[Evidence] = []

        # 1. 值符宫的门
        zhifu = chart.get("zhifu") or {}
        zhifu_palace_no = zhifu.get("palace")
        palaces = {p.get("palace"): p for p in (chart.get("palaces") or [])}
        zhifu_palace = palaces.get(zhifu_palace_no) or {}
        zhifu_door = zhifu_palace.get("door")
        zhifu_star = zhifu_palace.get("star")

        if zhifu_door:
            rule_ids.append(f"QIMEN-R-door-{zhifu_door}")
            if zhifu_door in JI_MEN:
                evidence.append(
                    Evidence(
                        source=EvidenceSource.TRADITIONAL_RULE,
                        rule_id=f"QIMEN-R-door-{zhifu_door}",
                        description=f"值符落宫门为{zhifu_door}（吉门），{zhifu_star}星值符得令",
                    )
                )
            elif zhifu_door in XIONG_MEN:
                counter.append(
                    Evidence(
                        source=EvidenceSource.TRADITIONAL_RULE,
                        rule_id=f"QIMEN-R-door-{zhifu_door}",
                        description=f"值符落宫门为{zhifu_door}（凶门）",
                    )
                )

        # 2. 格局（第 6.1 节：三奇/伏吟/反吟/门迫）
        pattern_signals: list[float] = []
        for pat in chart.get("detected_patterns") or []:
            name = pat.get("name", "")
            if name in PATTERN_DIRECTION:
                pattern_signals.append(PATTERN_DIRECTION[name])
                rule_ids.append(f"QIMEN-R-pattern-{name}")
                evidence.append(
                    Evidence(
                        source=EvidenceSource.TRADITIONAL_RULE,
                        rule_id=f"QIMEN-R-pattern-{name}",
                        description=f"格局「{name}」于{pat.get('palace')}宫：{pat.get('detail')}",
                    )
                )

        # 3. 融合：门 + 格局
        door_direction = 1.0 if zhifu_door in JI_MEN else (-1.0 if zhifu_door in XIONG_MEN else 0.0)
        net = door_direction * 0.5 + sum(pattern_signals) * 0.3
        if net == 0:
            return []  # 无明确信号，不强行输出

        direction = 1.0 if net > 0 else -1.0
        strength = min(0.8, 0.3 + abs(net))

        signals.append(
            Signal(
                **self._base_signal_kwargs(query),
                direction=direction,
                strength=round(strength, 3),
                confidence=0.34,  # 弱先验（禁止 6）
                evidence=evidence or [
                    Evidence(
                        source=EvidenceSource.TRADITIONAL_RULE,
                        rule_id="QIMEN-R-overall",
                        description=f"奇门盘（{chart.get('dun_type')}{chart.get('ju_number')}局，"
                                    f"{chart.get('yuan')}），值符{zhifu_star}星",
                    )
                ],
                counter_evidence=counter,
                rule_ids=rule_ids or ["QIMEN-R-overall"],
                dependency_group="lunar_calendar",  # 第 20.12 节：与八字同源历法
            )
        )
        return signals


registry.register(QimenAdapter())
