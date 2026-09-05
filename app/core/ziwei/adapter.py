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

ENGINE_VERSION = "ziwei-0.2.0"

# 十干四化表（通行版本）： → (禄, 权, 科, 忌)
STEM_MUTAGENS: dict[str, tuple[str, str, str, str]] = {
    "甲": ("廉贞", "破军", "武曲", "太阳"),
    "乙": ("天机", "天梁", "紫微", "太阴"),
    "丙": ("天同", "天机", "文昌", "廉贞"),
    "丁": ("太阴", "天同", "天机", "巨门"),
    "戊": ("贪狼", "太阴", "右弼", "天机"),
    "己": ("武曲", "贪狼", "天梁", "文曲"),
    "庚": ("太阳", "武曲", "太阴", "天同"),
    "辛": ("巨门", "太阳", "文曲", "文昌"),
    "壬": ("天梁", "紫微", "左辅", "武曲"),
    "癸": ("破军", "巨门", "太阴", "贪狼"),
}

# 紫微宫位中文名 → iztro 内部英文 id（horoscope.palace_names 用英文 id）
PALACE_EN = {
    "命宫": "soulPalace", "兄弟宫": "siblingsPalace", "夫妻宫": "spousePalace",
    "子女宫": "childrenPalace", "财帛宫": "wealthPalace", "疾厄宫": "healthPalace",
    "迁移宫": "travelPalace", "交友宫": "friendsPalace", "官禄宫": "careerPalace",
    "田宅宫": "propertyPalace", "福德宫": "spiritPalace", "父母宫": "parentsPalace",
}

# domain → 紫微宫位（传统对应）
DOMAIN_PALACE: dict[Domain, str] = {
    Domain.CAREER: "官禄宫",
    Domain.MONEY: "财帛宫",
    Domain.STUDY: "父母宫",
    Domain.SOCIAL: "交友宫",
    Domain.RELATIONSHIP: "夫妻宫",
    Domain.TRAVEL: "迁移宫",
    Domain.PROJECT: "官禄宫",
    Domain.HABIT: "福德宫",  # 福德主精神享受与癖好（习惯域更合传统口径）
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


_HEAVENLY_ZH = {
    "jiaHeavenly": "甲", "yiHeavenly": "乙", "bingHeavenly": "丙",
    "dingHeavenly": "丁", "wuHeavenly": "戊", "jiHeavenly": "己",
    "gengHeavenly": "庚", "xinHeavenly": "辛", "renHeavenly": "壬",
    "guiHeavenly": "癸",
}


def _stem_zh(stem: Any) -> str:
    return _HEAVENLY_ZH.get(str(stem), "")


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
        payload = self._to_payload(chart)

        # ---------- 运限层（流日/流月/流年）：让紫微信号随时间变化 ----------
        # 本命盘是静止的（每天算出来都一样），真正「哪一天是什么天气」靠运限。
        # horoscope(date).daily/monthly/yearly 给出该层干支与「各本命宫当前轮值什么宫」，
        # 例如 daily.palace_names[i] == 'spousePalace' 表示流日夫妻宫临本命第 i 宫。
        try:
            h = chart.horoscope(query.target_date.isoformat())
            flow: dict[str, Any] = {}
            for scale_key, layer_name in (
                ("day", "daily"),
                ("month", "monthly"),
                ("year", "yearly"),
            ):
                layer = getattr(h, layer_name, None)
                if layer is None:
                    continue
                flow[scale_key] = {
                    "layer_name": layer.name,
                    "stem": _stem_zh(getattr(layer, "heavenly_stem", "")),
                    # 本命宫 index → 该宫当前轮值的宫位 id
                    "palace_names": list(getattr(layer, "palace_names", []) or []),
                }
            payload["flow"] = flow
        except Exception:
            # 运限层失败不阻断本命层（降级而非报错）
            payload["flow"] = {}

        return payload

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
            3. 运限层（流日/流月/流年）：该 domain 宫临本命何宫、流干四化引动
               该宿主宫星曜 → 修正净值（让信号随时间变化，本命盘本身是静止的）。
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

        # ---------- 运限层：流X 目标宫临本命哪一宫 + 流干四化 ----------
        # 只用本命盘算紫微，每天信号都一样 —— 这是「静止盘当天气预报用」的伪精度。
        # 运限层把「当天流日夫妻宫临本命何宫、流干四化引动哪些星」纳入净值得分。
        flow_evidence: list[str] = []
        flow_payload = chart.get("flow") or {}
        flow_scale = query.time_scale.value
        # 周尺度以流月层论（流日只主当天，管不住整周）
        if flow_scale == "week":
            flow_scale = "month"
        layer = flow_payload.get(flow_scale) or {}
        palace_names = layer.get("palace_names") or []
        palace_en = PALACE_EN.get(target_palace or "")
        if palace_en and palace_en in palace_names:
            host_index = palace_names.index(palace_en)
            host = next(
                (p for p in chart.get("palaces", []) if p["index"] == host_index),
                None,
            )
            if host is not None:
                host_stars = host.get("major_stars", [])
                host_bright = any(s["is_bright"] for s in host_stars)
                host_weak = any(s["is_weak"] for s in host_stars)
                net += 0.3 if host_bright else (-0.2 if host_weak else 0.0)
                star_txt = "、".join(s["label"] for s in host_stars) or "无主星"
                flow_evidence.append(
                    f"{layer['layer_name']}{target_palace}临本命{host['name']}（{star_txt}）"
                )
                # 流干四化引动宿主宫星曜
                mu = STEM_MUTAGENS.get(layer.get("stem") or "")
                if mu:
                    labels = {s["label"] for s in host_stars}
                    for badge, star in zip(("禄", "权", "科", "忌"), mu):
                        if star in labels:
                            net += -0.4 if badge == "忌" else 0.3
                            flow_evidence.append(f"{layer['layer_name']}干化{badge}引动{star}")

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
        for fe in flow_evidence:
            evidence.append(
                Evidence(
                    source=EvidenceSource.TRADITIONAL_RULE,
                    rule_id=rule_id,
                    description=fe,
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
