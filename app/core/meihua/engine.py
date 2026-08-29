"""梅花易数排盘引擎（确定性自研）。

对应工程方案：
- 第 6.1 节 梅花易数（handsomejustin/meihua-yi 参考）
- 第 54 节：输入完全相同 → 排盘必须完全相同

承担：
    时间起卦 / 数字起卦 / 本卦 / 互卦 / 变卦 / 体用 / 五行

起卦法（时间起卦，deterministic）：
    上卦 = (年支序 + 月 + 日) % 8
    下卦 = (年支序 + 月 + 日 + 时支序) % 8
    动爻 = (年支序 + 月 + 日 + 时支序 + 分) % 6 + 1

体用：
    动爻所在卦为「用」，另一卦为「体」
    用生体 / 体克用 → 吉；用克体 / 体生用 → 凶；比和 → 平
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any

from app.core.calendar.core import CalendarCore

ENGINE_VERSION = "meihua-0.1.0"

TIANGAN = list("甲乙丙丁戊己庚辛壬癸")
ZHI_ORDER = list("子丑寅卯辰巳午未申酉戌亥")
ZHI_SEQ = {z: i + 1 for i, z in enumerate(ZHI_ORDER)}

# 先天八卦数 → 卦
XIAN_TIAN = {1: "乾", 2: "兑", 3: "离", 4: "震", 5: "巽", 6: "坎", 7: "艮", 8: "坤"}

# 八卦三爻（从下到上）
GUA_BITS = {
    "乾": (1, 1, 1), "兑": (1, 1, 0), "离": (1, 0, 1), "震": (1, 0, 0),
    "巽": (0, 1, 1), "坎": (0, 1, 0), "艮": (0, 0, 1), "坤": (0, 0, 0),
}

# 卦 → 五行
GUA_WUXING = {"乾": "金", "兑": "金", "离": "火", "震": "木", "巽": "木", "坎": "水", "艮": "土", "坤": "土"}

WUXING_SHENG = {"木": "火", "火": "土", "土": "金", "金": "水", "水": "木"}
WUXING_KE = {"木": "土", "土": "水", "水": "火", "火": "金", "金": "木"}

# 64 卦名（上下卦组合 → 卦名）
GUA_NAMES: dict[tuple[str, str], str] = {
    ("乾", "乾"): "乾为天", ("坤", "坤"): "坤为地", ("震", "震"): "震为雷",
    ("巽", "巽"): "巽为风", ("坎", "坎"): "坎为水", ("离", "离"): "离为火",
    ("艮", "艮"): "艮为山", ("兑", "兑"): "兑为泽",
    # 下卦, 上卦
    ("震", "坤"): "地雷复", ("兑", "坤"): "地泽临", ("乾", "坤"): "地天泰",
    ("乾", "震"): "雷天大壮", ("乾", "兑"): "泽天夬", ("坎", "乾"): "水天需",
    ("坤", "坎"): "水地比", ("巽", "乾"): "天风姤", ("艮", "乾"): "天山遁",
    ("坤", "乾"): "天地否", ("坤", "巽"): "风地观", ("艮", "坤"): "山地剥",
    ("离", "坤"): "火地晋", ("离", "乾"): "火天大有", ("震", "坤"): "地雷复",
    ("兑", "震"): "雷泽归妹", ("艮", "兑"): "泽山咸", ("坎", "兑"): "泽水困",
    ("坤", "兑"): "泽地萃", ("艮", "坎"): "水山蹇", ("艮", "坤"): "山地剥",
    ("艮", "震"): "雷山小过", ("巽", "艮"): "风山渐", ("兑", "艮"): "山泽损",
    ("巽", "坎"): "水风井", ("离", "震"): "雷火丰", ("离", "坎"): "水火既济",
    ("坎", "离"): "火水未济", ("巽", "离"): "火风鼎", ("艮", "离"): "火山旅",
    ("兑", "离"): "火泽睽", ("兑", "巽"): "泽风大过", ("坎", "震"): "雷水解",
    ("坎", "巽"): "风水涣", ("离", "巽"): "风火家人", ("离", "艮"): "山火贲",
    ("兑", "坎"): "水泽节", ("震", "坎"): "水雷屯", ("震", "离"): "火雷噬嗑",
    ("巽", "震"): "雷风恒", ("坤", "震"): "雷地豫", ("坎", "坤"): "地水师",
    ("艮", "巽"): "山风蛊", ("乾", "巽"): "风天小畜", ("乾", "离"): "天火同人",
    ("乾", "艮"): "山天大畜", ("乾", "兑"): "泽天夬", ("兑", "乾"): "天泽履",
    ("离", "兑"): "泽火革", ("震", "兑"): "泽雷随", ("坤", "巽"): "风地观",
    ("巽", "坤"): "地风升", ("震", "艮"): "山雷颐", ("艮", "巽"): "山风蛊",
    ("坎", "艮"): "山水蒙", ("兑", "艮"): "山泽损", ("巽", "兑"): "泽风大过",
    ("离", "坤"): "火地晋", ("艮", "震"): "雷山小过", ("坎", "震"): "雷水解",
    ("震", "巽"): "雷风恒", ("巽", "坎"): "水风井", ("震", "坎"): "水雷屯",
    ("兑", "巽"): "泽风大过", ("艮", "巽"): "山风蛊", ("坎", "巽"): "风水涣",
    ("离", "巽"): "风火家人", ("坤", "兑"): "泽地萃", ("艮", "兑"): "泽山咸",
}


def cast_hexagram(
    dt: datetime, *, year_branch: str, hour_branch: str
) -> dict[str, Any]:
    """时间起卦 → 本卦/互卦/变卦/体用。

    dt：起卦时刻（year_branch/hour_branch 由 CalendarCore 提供）
    """
    seq = ZHI_SEQ[year_branch]
    month = dt.month
    day = dt.day
    upper_num = (seq + month + day) % 8 or 8
    lower_num = (seq + month + day + ZHI_SEQ[hour_branch]) % 8 or 8
    moving = (seq + month + day + ZHI_SEQ[hour_branch] + dt.minute) % 6 + 1

    upper = XIAN_TIAN[upper_num]
    lower = XIAN_TIAN[lower_num]

    # 本卦六爻（初爻→上爻）：下卦 + 上卦
    ben_lines = list(GUA_BITS[lower]) + list(GUA_BITS[upper])

    # 动爻（1-6，初爻=1）
    moving_idx = moving - 1
    yin_yang = ben_lines[moving_idx]
    ben_lines[moving_idx] = 1 - yin_yang  # 变卦：动爻阴阳互变
    bian_lines = list(ben_lines)
    ben_lines[moving_idx] = yin_yang  # 还原本卦

    # 互卦：本卦 2/3/4 爻为下互，3/4/5 爻为上互
    hu_lines = ben_lines[1:4] + ben_lines[2:5]
    hu_lower = _bits_to_gua(hu_lines[:3])
    hu_upper = _bits_to_gua(hu_lines[3:])

    # 体用：动爻在 1-3（下卦）→ 下为用，上为体；4-6 → 上为用，下为体
    yong_in_upper = moving_idx >= 3
    ti_gua, yong_gua = (upper, lower) if yong_in_upper else (lower, upper)

    ti_wx = GUA_WUXING[ti_gua]
    yong_wx = GUA_WUXING[yong_gua]

    # 五行生克关系
    if ti_wx == yong_wx:
        relation = "比和"
    elif WUXING_SHENG.get(yong_wx) == ti_wx:
        relation = "用生体"
    elif WUXING_KE.get(ti_wx) == yong_wx:
        relation = "体克用"
    elif WUXING_SHENG.get(ti_wx) == yong_wx:
        relation = "体生用"
    else:
        relation = "用克体"

    # 吉凶方向：用生体/体克用 → 吉；用克体/体生用 → 凶；比和 → 平
    if relation in ("用生体", "体克用"):
        direction = 1.0
    elif relation in ("用克体", "体生用"):
        direction = -1.0
    else:
        direction = 0.0

    ben_name = GUA_NAMES.get((lower, upper), f"{lower}{upper}")

    return {
        "engine": ENGINE_VERSION,
        "cast_time": dt.isoformat(),
        "ben_gua": {"upper": upper, "lower": lower, "name": ben_name, "lines": ben_lines},
        "hu_gua": {"upper": hu_upper, "lower": hu_lower,
                   "name": GUA_NAMES.get((hu_lower, hu_upper), f"{hu_lower}{hu_upper}"),
                   "lines": hu_lines},
        "bian_gua": {"upper": upper, "lower": lower,
                     "name": GUA_NAMES.get((_bits_to_gua(bian_lines[:3]), _bits_to_gua(bian_lines[3:])),
                                           f"{_bits_to_gua(bian_lines[:3])}{_bits_to_gua(bian_lines[3:])}"),
                     "lines": bian_lines},
        "moving_yao": moving,
        "ti_gua": ti_gua, "yong_gua": yong_gua,
        "ti_wuxing": ti_wx, "yong_wuxing": yong_wx,
        "relation": relation,
        "direction": direction,
        "input_hash": hashlib.sha256(
            f"meihua:{dt.isoformat()}:{year_branch}:{hour_branch}".encode()
        ).hexdigest(),
    }


def _bits_to_gua(bits: list[int]) -> str:
    for gua, gb in GUA_BITS.items():
        if list(gb) == bits:
            return gua
    return "?"


def cast_by_time(dt: datetime) -> dict[str, Any]:
    """便捷入口：完整起卦（自动取四柱）。"""
    core = CalendarCore()
    cal = core.compute(
        birth_date=dt.date(), birth_time=f"{dt.hour:02d}:{dt.minute:02d}",
        target_date=dt.date(), target_time=f"{dt.hour:02d}:{dt.minute:02d}",
        gender="unknown",
    )
    if cal.degraded:
        year_branch = ZHI_ORDER[(dt.year - 1900) % 12]
    else:
        year_gz = str(cal.payload.get("year_ganzhi", ""))
        year_branch = year_gz[1] if len(year_gz) > 1 else ZHI_ORDER[(dt.year - 1900) % 12]

    hour_branch = ZHI_ORDER[((dt.hour + 1) // 2) % 12]
    return cast_hexagram(dt, year_branch=year_branch, hour_branch=hour_branch)
