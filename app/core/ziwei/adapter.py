"""ZiweiAdapter —— 紫微斗数信号。

对应工程方案：
- 第 6.1 节 紫微斗数（SylarLong/iztro 参考）
- 第 14 节 统一 Signal Schema
- 第 53 节 Adapter 策略

引擎：iztro-py（纯 Python 紫微排盘，by_solar）。
第 54 节：程序负责排盘，LLM 不允许自己算命盘。
"""

from __future__ import annotations

from datetime import date
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

ENGINE_VERSION = "ziwei-0.1.0"

# domain → 紫微宫位（传统对应）
DOMAIN_PALACE: dict[Domain, str] = {
    Domain.CAREER: "官禄宫",
    Domain.MONEY: "财帛宫",
    Domain.STUDY: "父母宫",
    Domain.SOCIAL: "交友宫",
    Domain.RELATIONSHIP: "夫妻宫",
    Domain.TRAVEL: "迁移宫",
    Domain.PROJECT: "官禄宫",
    Domain.HABIT: "命宫",
    Domain.PURCHASE: "财帛宫",
    Domain.COMMUNICATION: "交友宫",
    Domain.SCHEDULE: "命宫",
    Domain.UNEXPECTED_EVENT: "命宫",
}

# 第 6.1 节：空宫借对宫星曜（借星安宫）
PALACE_COUNTER: dict[str, str] = {
    "官禄宫": "夫妻宫", "夫妻宫": "官禄宫",
    "财帛宫": "福德宫", "福德宫": "财帛宫",
    "父母宫": "疾厄宫", "疾厄宫": "父母宫",
    "交友宫": "兄弟宫", "兄弟宫": "交友宫",
    "命宫": "迁移宫", "迁移宫": "命宫",
    "子女宫": "田宅宫", "田宅宫": "子女宫",
}


def _hour_to_time_index(hour: int) -> int:
    """小时 → iztro 时辰索引（0-12）。"""
    return min((hour + 1) // 2, 12)


class ZiweiAdapter(MetaphysicalAdapter):
    source = SourceType.ZIWEI
    engine_name = "iztro-py"
    engine_version = ENGINE_VERSION

    @property
    def available(self) -> bool:
        try:
            from iztro_py import astro  # noqa: F401

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
        if profile is None:
            return {}

        try:
            from iztro_py import astro
        except ImportError:
            return {}

        try:
            h, m = (query.target_time or "00:00").split(":")
            hour = int(h)
        except (ValueError, AttributeError):
            hour = 0

        gender = "男" if profile.gender == "male" else ("女" if profile.gender == "female" else "男")
        chart = astro.by_solar(
            profile.solar_birth_date.isoformat(),
            _hour_to_time_index(hour),
            gender,
        )

        # 结构化输出
        return self._to_payload(chart)

    # ------------------------------------------------------------------
    def _to_payload(self, chart: Any) -> dict[str, Any]:
        """Astrolabe → 结构化 dict。"""
        palaces = []
        for p in chart.palaces:
            palaces.append(
                {
                    "name": p.translate_name(),
                    "index": p.index,
                    "major_stars": [
                        {
                            "name": s.name,
                            "label": s.translate_name(),
                            "brightness": s.brightness,
                            "mutagen": s.mutagen,
                            "is_bright": s.is_bright() if hasattr(s, "is_bright") else False,
                            "is_weak": s.is_weak() if hasattr(s, "is_weak") else False,
                        }
                        for s in (p.major_stars or [])
                    ],
                }
            )
        soul = chart.get_soul_palace()
        return {
            "palaces": palaces,
            "soul_palace": soul.translate_name() if soul else "",
            "soul_major_stars": [
                s.translate_name() for s in (soul.major_stars if soul else [])
            ],
            "four_pillars": chart.four_pillars if hasattr(chart, "four_pillars") else None,
        }

    # ------------------------------------------------------------------
    def to_signals(self, query: AdapterQuery, chart: dict[str, Any]) -> list[Signal]:
        """命盘 → Signal。

        规则（骨架，待验证）：
            1. 目标 domain 对应宫的主星亮度：庙/旺/得 → 正向，陷/弱 → 负向；
            2. 四化星落该宫 → 增强方向（禄/权/科 正，忌 负）；
            3. 命宫主星整体状态作为基础。
        """
        target_palace = DOMAIN_PALACE.get(query.domain)
        palace = next(
            (p for p in chart.get("palaces", []) if p["name"] == target_palace),
            None,
        )
        if palace is None:
            return []

        stars = palace.get("major_stars", [])
        borrowed = False
        if not stars:
            # 空宫：借对宫星曜（第 6.1 节「借星安宫」）
            counter = PALACE_COUNTER.get(target_palace)
            if counter:
                palace = next(
                    (p for p in chart.get("palaces", []) if p["name"] == counter),
                    None,
                )
                stars = palace.get("major_stars", []) if palace else []
                borrowed = bool(stars)
        if not stars:
            return []

        # 亮度方向
        bright_any = any(s["is_bright"] for s in stars)
        weak_any = any(s["is_weak"] for s in stars)

        # 四化
        mutagen_val = 0.0
        mutagen_labels = []
        for s in stars:
            m = s.get("mutagen")
            if m in ("禄", "权", "科"):
                mutagen_val += 0.5
                mutagen_labels.append(f"{s['label']}{m}")
            elif m == "忌":
                mutagen_val -= 0.5
                mutagen_labels.append(f"{s['label']}忌")

        net = (0.5 if bright_any else -0.3 if weak_any else 0.0) + mutagen_val
        if net == 0:
            return []

        direction = 1.0 if net > 0 else -1.0
        strength = min(0.8, 0.25 + abs(net))

        star_labels = [s["label"] for s in stars]
        rule_id = f"ZIWEI-R-{target_palace}-{query.domain.value}"
        palace_label = target_palace
        if borrowed:
            palace_label = f"{target_palace}（借{palace['name']}星）"

        evidence = [
            Evidence(
                source=EvidenceSource.TRADITIONAL_RULE,
                rule_id=rule_id,
                description=(
                    f"{palace_label}主星 {'、'.join(star_labels)}"
                    f"（亮度 {'、'.join(s['brightness'] or '平' for s in stars)}）"
                ),
            )
        ]
        if mutagen_labels:
            evidence.append(
                Evidence(
                    source=EvidenceSource.TRADITIONAL_RULE,
                    rule_id=rule_id,
                    description=f"四化：{'、'.join(mutagen_labels)}",
                )
            )

        return [
            Signal(
                **self._base_signal_kwargs(query),
                direction=direction,
                strength=round(strength, 3),
                confidence=0.33,  # 弱先验（禁止 6）
                evidence=evidence,
                counter_evidence=(
                    [
                        Evidence(
                            source=EvidenceSource.TRADITIONAL_RULE,
                            rule_id=rule_id,
                            description=f"{target_palace}星曜陷弱或带忌",
                        )
                    ]
                    if (weak_any and not bright_any)
                    else []
                ),
                rule_ids=[rule_id],
                dependency_group="lunar_calendar",  # 第 20.12 节
            )
        ]


registry.register(ZiweiAdapter())
