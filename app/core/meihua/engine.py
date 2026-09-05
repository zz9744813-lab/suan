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

ENGINE_VERSION = "meihua-0.2.0"

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

# 64 卦名表：(下卦, 上卦) → 卦名。
# 不再手写 —— 由六爻 HEXAGRAMS（pattern→name 权威表，经逐卦对抗校验）
# 程序化生成。手写表曾被对抗性审计出 9 条上下卦颠倒（如 (离,乾)
# 误作「火天大有」，实为「天火同人」）且仅覆盖 60 卦，故单一事实源化。
def _build_gua_names() -> dict[tuple[str, str], str]:
    from app.core.liuyao.engine import HEXAGRAMS

    _bits2gua = {tuple(v): k for k, v in GUA_BITS.items()}
    table: dict[tuple[str, str], str] = {}
    for pat, e in HEXAGRAMS.items():
        bits = [int(x) for x in pat.split(",")]
        table[(_bits2gua[tuple(bits[:3])], _bits2gua[tuple(bits[3:])])] = e["name"]
    return table


GUA_NAMES: dict[tuple[str, str], str] = _build_gua_names()


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

    # 变卦的上下卦按变卦爻位重新取（曾误用本卦的 upper/lower）
    bian_lower = _bits_to_gua(bian_lines[:3])
    bian_upper = _bits_to_gua(bian_lines[3:])

    return {
        "engine": ENGINE_VERSION,
        "cast_time": dt.isoformat(),
        "ben_gua": {"upper": upper, "lower": lower, "name": ben_name, "lines": ben_lines},
        "hu_gua": {"upper": hu_upper, "lower": hu_lower,
                   "name": GUA_NAMES.get((hu_lower, hu_upper), f"{hu_lower}{hu_upper}"),
                   "lines": hu_lines},
        "bian_gua": {"upper": bian_upper, "lower": bian_lower,
                     "name": GUA_NAMES.get((bian_lower, bian_upper),
                                           f"{bian_lower}{bian_upper}"),
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
