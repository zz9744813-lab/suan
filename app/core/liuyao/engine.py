"""六爻排盘引擎（确定性）。

移植自 xiongdun8/liuyao（MIT 协议）的排盘核心，
按玄鉴架构改造：

1. 起卦改用「时间起卦法」—— 系统预测必须 deterministic（第 54 节），
   不能用随机摇卦；
2. 四柱干支改用玄鉴 CalendarCore（lunar-python）计算，更精确；
3. 输出为结构化卦盘，供 LiuyaoAdapter 转 Signal（第 14 节）。

保留原项目已验证的排盘逻辑：纳甲 / 六亲 / 六神 / 世应 / 旺衰 / 旬空 / 入墓 / 回头生克。

工程方案：
- 第 6.1 节 六爻（Johnson-Jia/liuyao-divination 参考架构）
- 第 54 节：输入完全相同 → 排盘必须完全相同
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.core.calendar.core import CalendarCore

ENGINE_VERSION = "liuyao-0.1.0"

# ----------------------------------------------------------------------
# 常量表
# ----------------------------------------------------------------------
BRANCH_WUXING = {
    "子": "水", "丑": "土", "寅": "木", "卯": "木",
    "辰": "土", "巳": "火", "午": "火", "未": "土",
    "申": "金", "酉": "金", "戌": "土", "亥": "水",
}

CONFLICT_BRANCH = {  # 相冲
    "子": "午", "午": "子", "丑": "未", "未": "丑",
    "寅": "申", "申": "寅", "卯": "酉", "酉": "卯",
    "辰": "戌", "戌": "辰", "巳": "亥", "亥": "巳",
}

COMBINE_BRANCH = {  # 六合
    "子": "丑", "丑": "子", "寅": "亥", "亥": "寅",
    "卯": "戌", "戌": "卯", "辰": "酉", "酉": "辰",
    "巳": "申", "申": "巳", "午": "未", "未": "午",
}

TOMB_BRANCH = {  # 入墓
    "木": "未", "火": "戌", "金": "丑", "水": "辰",
    "土": ["辰", "戌", "丑", "未"],
}

GENERATE_WUXING = {"木": "火", "火": "土", "土": "金", "金": "水", "水": "木"}
CONQUER_WUXING = {"木": "土", "土": "水", "水": "火", "火": "金", "金": "木"}
IMPERIAL_WANG = {"木": "卯", "火": "午", "金": "酉", "水": "子", "土": ["辰", "戌", "丑", "未"]}
EXTINCTION = {"木": "申", "火": "亥", "金": "寅", "水": "巳", "土": "亥"}

LIUSHOU = ["青龙", "朱雀", "勾陈", "螣蛇", "白虎", "玄武"]

XUN_KONG = {
    "甲子": ["戌", "亥"], "甲戌": ["申", "酉"], "甲申": ["午", "未"],
    "甲午": ["辰", "巳"], "甲辰": ["寅", "卯"], "甲寅": ["子", "丑"],
}
XUN_STARTS = ["甲子", "甲戌", "甲申", "甲午", "甲辰", "甲寅"]

GAN_ORDER = list("甲乙丙丁戊己庚辛壬癸")
ZHI_ORDER = list("子丑寅卯辰巳午未申酉戌亥")

# 纳甲地支（第 6.1 节：阳卦顺行、阴卦逆行）
HEXAGRAM_EARTHLY_BRANCH = {
    "乾宫": ["子", "寅", "辰", "午", "申", "戌"],
    "坤宫": ["未", "巳", "卯", "丑", "亥", "酉"],
    "震宫": ["子", "寅", "辰", "午", "申", "戌"],
    "巽宫": ["丑", "亥", "酉", "未", "巳", "卯"],
    "坎宫": ["寅", "辰", "午", "申", "戌", "子"],
    "离宫": ["卯", "丑", "亥", "酉", "未", "巳"],
    "艮宫": ["辰", "午", "申", "戌", "子", "寅"],
    "兑宫": ["巳", "卯", "丑", "亥", "酉", "未"],
}

# 卦宫五行（第 6.1 节六亲判定基准）
PALACE_WUXING = {
    "乾宫": "金", "兑宫": "金", "离宫": "火", "震宫": "木",
    "巽宫": "木", "坎宫": "水", "艮宫": "土", "坤宫": "土",
}

# 64 卦表：键 = 六爻阴阳串（初爻→上爻），值 = 宫/世/应/类型/名
HEXAGRAMS: dict[str, dict[str, Any]] = {
    "1,1,1,1,1,1": {"palace": "乾宫", "shi": 5, "ying": 2, "type": "本宫卦", "name": "乾为天"},
    "0,1,1,1,1,1": {"palace": "乾宫", "shi": 0, "ying": 3, "type": "一世卦", "name": "天风姤"},
    "0,0,1,1,1,1": {"palace": "乾宫", "shi": 1, "ying": 4, "type": "二世卦", "name": "天山遁"},
    "0,0,0,1,1,1": {"palace": "乾宫", "shi": 2, "ying": 5, "type": "三世卦", "name": "天地否"},
    "0,0,0,0,1,1": {"palace": "乾宫", "shi": 3, "ying": 0, "type": "四世卦", "name": "风地观"},
    "0,0,0,0,0,1": {"palace": "乾宫", "shi": 4, "ying": 1, "type": "五世卦", "name": "山地剥"},
    "0,0,0,1,0,1": {"palace": "乾宫", "shi": 3, "ying": 0, "type": "游魂卦", "name": "火地晋"},
    "1,1,1,1,0,1": {"palace": "乾宫", "shi": 2, "ying": 5, "type": "归魂卦", "name": "火天大有"},
    "0,0,0,0,0,0": {"palace": "坤宫", "shi": 5, "ying": 2, "type": "本宫卦", "name": "坤为地"},
    "1,0,0,0,0,0": {"palace": "坤宫", "shi": 0, "ying": 3, "type": "一世卦", "name": "地雷复"},
    "1,1,0,0,0,0": {"palace": "坤宫", "shi": 1, "ying": 4, "type": "二世卦", "name": "地泽临"},
    "1,1,1,0,0,0": {"palace": "坤宫", "shi": 2, "ying": 5, "type": "三世卦", "name": "地天泰"},
    "1,1,1,1,0,0": {"palace": "坤宫", "shi": 3, "ying": 0, "type": "四世卦", "name": "雷天大壮"},
    "1,1,1,1,1,0": {"palace": "坤宫", "shi": 4, "ying": 1, "type": "五世卦", "name": "泽天夬"},
    "1,1,1,0,1,0": {"palace": "坤宫", "shi": 3, "ying": 0, "type": "游魂卦", "name": "水天需"},
    "0,0,0,0,1,0": {"palace": "坤宫", "shi": 2, "ying": 5, "type": "归魂卦", "name": "水地比"},
    "1,0,0,1,0,0": {"palace": "震宫", "shi": 5, "ying": 2, "type": "本宫卦", "name": "震为雷"},
    "0,0,0,1,0,0": {"palace": "震宫", "shi": 0, "ying": 3, "type": "一世卦", "name": "雷地豫"},
    "0,1,0,1,0,0": {"palace": "震宫", "shi": 1, "ying": 4, "type": "二世卦", "name": "雷水解"},
    "0,1,1,1,0,0": {"palace": "震宫", "shi": 2, "ying": 5, "type": "三世卦", "name": "雷风恒"},
    "0,1,1,0,0,0": {"palace": "震宫", "shi": 3, "ying": 0, "type": "四世卦", "name": "地风升"},
    "0,1,1,0,1,0": {"palace": "震宫", "shi": 4, "ying": 1, "type": "五世卦", "name": "水风井"},
    "0,1,1,1,1,0": {"palace": "震宫", "shi": 3, "ying": 0, "type": "游魂卦", "name": "泽风大过"},
    "1,0,0,1,1,0": {"palace": "震宫", "shi": 2, "ying": 5, "type": "归魂卦", "name": "泽雷随"},
    "0,1,1,0,1,1": {"palace": "巽宫", "shi": 5, "ying": 2, "type": "本宫卦", "name": "巽为风"},
    "1,1,1,0,1,1": {"palace": "巽宫", "shi": 0, "ying": 3, "type": "一世卦", "name": "风天小畜"},
    "1,0,1,0,1,1": {"palace": "巽宫", "shi": 1, "ying": 4, "type": "二世卦", "name": "风火家人"},
    "1,0,0,0,1,1": {"palace": "巽宫", "shi": 2, "ying": 5, "type": "三世卦", "name": "风雷益"},
    "1,0,0,1,1,1": {"palace": "巽宫", "shi": 3, "ying": 0, "type": "四世卦", "name": "天雷无妄"},
    "1,0,0,1,0,1": {"palace": "巽宫", "shi": 4, "ying": 1, "type": "五世卦", "name": "火雷噬嗑"},
    "1,0,0,0,0,1": {"palace": "巽宫", "shi": 3, "ying": 0, "type": "游魂卦", "name": "山雷颐"},
    "0,1,1,0,0,1": {"palace": "巽宫", "shi": 2, "ying": 5, "type": "归魂卦", "name": "山风蛊"},
    "0,1,0,0,1,0": {"palace": "坎宫", "shi": 5, "ying": 2, "type": "本宫卦", "name": "坎为水"},
    "1,1,0,0,1,0": {"palace": "坎宫", "shi": 0, "ying": 3, "type": "一世卦", "name": "水泽节"},
    "1,0,0,0,1,0": {"palace": "坎宫", "shi": 1, "ying": 4, "type": "二世卦", "name": "水雷屯"},
    "1,0,1,0,1,0": {"palace": "坎宫", "shi": 2, "ying": 5, "type": "三世卦", "name": "水火既济"},
    "1,0,1,1,1,0": {"palace": "坎宫", "shi": 3, "ying": 0, "type": "四世卦", "name": "泽火革"},
    "1,0,1,1,0,0": {"palace": "坎宫", "shi": 4, "ying": 1, "type": "五世卦", "name": "雷火丰"},
    "1,0,1,0,0,0": {"palace": "坎宫", "shi": 3, "ying": 0, "type": "游魂卦", "name": "地火明夷"},
    "0,1,0,0,0,0": {"palace": "坎宫", "shi": 2, "ying": 5, "type": "归魂卦", "name": "地水师"},
    "1,0,1,1,0,1": {"palace": "离宫", "shi": 5, "ying": 2, "type": "本宫卦", "name": "离为火"},
    "0,0,1,1,0,1": {"palace": "离宫", "shi": 0, "ying": 3, "type": "一世卦", "name": "火山旅"},
    "0,1,1,1,0,1": {"palace": "离宫", "shi": 1, "ying": 4, "type": "二世卦", "name": "火风鼎"},
    "0,1,0,1,0,1": {"palace": "离宫", "shi": 2, "ying": 5, "type": "三世卦", "name": "火水未济"},
    "0,1,0,0,0,1": {"palace": "离宫", "shi": 3, "ying": 0, "type": "四世卦", "name": "山水蒙"},
    "0,1,0,0,1,1": {"palace": "离宫", "shi": 4, "ying": 1, "type": "五世卦", "name": "风水涣"},
    "0,1,0,1,1,1": {"palace": "离宫", "shi": 3, "ying": 0, "type": "游魂卦", "name": "天水讼"},
    "1,0,1,1,1,1": {"palace": "离宫", "shi": 2, "ying": 5, "type": "归魂卦", "name": "天火同人"},
    "0,0,1,0,0,1": {"palace": "艮宫", "shi": 5, "ying": 2, "type": "本宫卦", "name": "艮为山"},
    "1,0,1,0,0,1": {"palace": "艮宫", "shi": 0, "ying": 3, "type": "一世卦", "name": "山火贲"},
    "1,1,1,0,0,1": {"palace": "艮宫", "shi": 1, "ying": 4, "type": "二世卦", "name": "山天大畜"},
    "1,1,0,0,0,1": {"palace": "艮宫", "shi": 2, "ying": 5, "type": "三世卦", "name": "山泽损"},
    "1,1,0,1,0,1": {"palace": "艮宫", "shi": 3, "ying": 0, "type": "四世卦", "name": "火泽睽"},
    "1,1,0,1,1,1": {"palace": "艮宫", "shi": 4, "ying": 1, "type": "五世卦", "name": "天泽履"},
    "1,1,0,0,1,1": {"palace": "艮宫", "shi": 3, "ying": 0, "type": "游魂卦", "name": "风泽中孚"},
    "0,0,1,0,1,1": {"palace": "艮宫", "shi": 2, "ying": 5, "type": "归魂卦", "name": "风山渐"},
    "1,1,0,1,1,0": {"palace": "兑宫", "shi": 5, "ying": 2, "type": "本宫卦", "name": "兑为泽"},
    "0,1,0,1,1,0": {"palace": "兑宫", "shi": 0, "ying": 3, "type": "一世卦", "name": "泽水困"},
    "0,0,0,1,1,0": {"palace": "兑宫", "shi": 1, "ying": 4, "type": "二世卦", "name": "泽地萃"},
    "0,0,1,1,1,0": {"palace": "兑宫", "shi": 2, "ying": 5, "type": "三世卦", "name": "泽山咸"},
    "0,0,1,0,1,0": {"palace": "兑宫", "shi": 3, "ying": 0, "type": "四世卦", "name": "水山蹇"},
    "0,0,1,0,0,0": {"palace": "兑宫", "shi": 4, "ying": 1, "type": "五世卦", "name": "地山谦"},
    "0,0,1,1,0,0": {"palace": "兑宫", "shi": 3, "ying": 0, "type": "游魂卦", "name": "雷山小过"},
    "1,1,0,1,0,0": {"palace": "兑宫", "shi": 2, "ying": 5, "type": "归魂卦", "name": "雷泽归妹"},
}

# 八卦（先天序）→ 五行
GUA_WUXING = {"乾": "金", "兑": "金", "离": "火", "震": "木", "巽": "木", "坎": "水", "艮": "土", "坤": "土"}

# 先天八卦数 → 卦
XIAN_TIAN = {1: "乾", 2: "兑", 3: "离", 4: "震", 5: "巽", 6: "坎", 7: "艮", 8: "坤"}

# 时间起卦用：地支序号（子1...亥12）
ZHI_SEQ = {z: i + 1 for i, z in enumerate(ZHI_ORDER)}

POSITIONS = ["初爻", "二爻", "三爻", "四爻", "五爻", "上爻"]


# ----------------------------------------------------------------------
# 起卦（deterministic 时间起卦法）
# ----------------------------------------------------------------------
def cast_by_time(
    dt: datetime,
    *,
    year_branch: str,
    month: int,
    day: int,
    hour_branch: str,
    minute: int,
) -> list[int]:
    """梅花式时间起卦 → 六爻编码（初爻→上爻）。

    编码：1=少阴 2=少阳 3=纯阳(动) 4=纯阴(动)

    上卦 = (年支序 + 月 + 日) % 8（0→8）
    下卦 = (年支序 + 月 + 日 + 时支序) % 8
    动爻 = (年支序 + 月 + 日 + 时支序 + 分) % 6 + 1
    """
    seq = ZHI_SEQ[year_branch]
    upper_num = (seq + month + day) % 8 or 8
    lower_num = (seq + month + day + ZHI_SEQ[hour_branch]) % 8 or 8
    moving = (seq + month + day + ZHI_SEQ[hour_branch] + minute) % 6 + 1

    upper_gua = XIAN_TIAN[upper_num]  # 上卦（外卦）
    lower_gua = XIAN_TIAN[lower_num]  # 下卦（内卦）

    # 八卦三爻（从下到上），先天八卦数序
    GUA_BITS = {
        "乾": (1, 1, 1), "兑": (1, 1, 0), "离": (1, 0, 1), "震": (1, 0, 0),
        "巽": (0, 1, 1), "坎": (0, 1, 0), "艮": (0, 0, 1), "坤": (0, 0, 0),
    }

    # 六爻（初爻→上爻）：下卦三爻 + 上卦三爻
    lines = list(GUA_BITS[lower_gua]) + list(GUA_BITS[upper_gua])

    # 动爻编码：阳动=3 阴动=4
    idx = moving - 1
    lines[idx] = 3 if lines[idx] == 1 else 4

    return lines


def generate_changed(original: list[int]) -> list[int]:
    """纯阳(3)→少阴(1)，纯阴(4)→少阳(2)。"""
    return [1 if x == 3 else (2 if x == 4 else x) for x in original]


def to_binary(hexagram: list[int]) -> str:
    """六爻编码 → 阴阳串（初爻→上爻，0阴1阳）。"""
    return ",".join("1" if x in (2, 3) else "0" for x in hexagram)


def get_palace(hexagram: list[int]) -> dict[str, Any] | None:
    return HEXAGRAMS.get(to_binary(hexagram))


# ----------------------------------------------------------------------
# 旬空 / 六亲 / 六神
# ----------------------------------------------------------------------
def get_xunkong(day_ganzhi: str) -> list[str]:
    """按日柱算旬空。"""
    dg, dz = day_ganzhi[0], day_ganzhi[1]
    d_idx = GAN_ORDER.index(dg) * 12 + ZHI_ORDER.index(dz)
    for i, start in enumerate(XUN_STARTS):
        s_idx = GAN_ORDER.index(start[0]) * 12 + ZHI_ORDER.index(start[1])
        if i == len(XUN_STARTS) - 1:
            if d_idx >= s_idx or d_idx <= s_idx + 11:
                return XUN_KONG[start]
        elif s_idx <= d_idx <= s_idx + 11:
            return XUN_KONG[start]
    return ["", ""]


def get_liushou_order(day_branch: str) -> list[str]:
    """第 6.1 节：按日支起六神。"""
    start = ZHI_ORDER.index(day_branch) % 6
    return [LIUSHOU[(start + i) % 6] for i in range(6)]


def get_liuqin(wo_wuxing: str, target_wuxing: str) -> str:
    """第 6.1 节六亲：以卦宫五行为「我」。"""
    if target_wuxing == wo_wuxing:
        return "兄弟"
    if GENERATE_WUXING.get(target_wuxing) == wo_wuxing:
        return "父母"
    if GENERATE_WUXING.get(wo_wuxing) == target_wuxing:
        return "子孙"
    if CONQUER_WUXING.get(target_wuxing) == wo_wuxing:
        return "官鬼"
    return "妻财"


# ----------------------------------------------------------------------
# 旺衰
# ----------------------------------------------------------------------
def calculate_yao_strength(
    yao_branch: str, month_branch: str, day_branch: str,
    changed_yao_branch: str | None = None, is_moving_yao: bool = False,
) -> dict[str, Any]:
    """单爻旺衰得分（移植 xiongdun8/liuyao.wangshuai）。"""
    score = 0.0
    status: list[str] = []
    yao_wx = BRANCH_WUXING[yao_branch]
    month_wx = BRANCH_WUXING[month_branch]
    day_wx = BRANCH_WUXING[day_branch]

    if yao_branch == month_branch:
        score += 2.0; status.append("月建")
    if yao_branch == day_branch:
        score += 1.5; status.append("日建")

    if COMBINE_BRANCH.get(yao_branch) == month_branch:
        if CONQUER_WUXING.get(month_wx) == yao_wx or CONQUER_WUXING.get(yao_wx) == month_wx:
            score -= 0.5; status.append("月合克")
        else:
            score += 1.5; status.append("合旺")
    if COMBINE_BRANCH.get(yao_branch) == day_branch:
        if CONQUER_WUXING.get(day_wx) == yao_wx or CONQUER_WUXING.get(yao_wx) == day_wx:
            score -= 0.5; status.append("日合克")
        else:
            score += 1.5; status.append("合绊")

    if GENERATE_WUXING.get(month_wx) == yao_wx:
        score += 1.5; status.append("月生")
    if GENERATE_WUXING.get(day_wx) == yao_wx:
        score += 1.5; status.append("日生")
    if month_wx == yao_wx and yao_branch != month_branch:
        score += 1.0; status.append("月扶")
    if day_wx == yao_wx and yao_branch != day_branch:
        score += 0.5; status.append("日扶")
    if CONFLICT_BRANCH.get(yao_branch) == month_branch:
        score -= 2.0; status.append("月破")
    if CONQUER_WUXING.get(month_wx) == yao_wx:
        score -= 1.0; status.append("月克")
    if CONQUER_WUXING.get(day_wx) == yao_wx:
        score -= 1.0; status.append("日克")

    is_day_conflict = CONFLICT_BRANCH.get(yao_branch) == day_branch
    if is_day_conflict and score < 0:
        score -= 1.5; status.append("日散")

    # 帝旺
    dw = IMPERIAL_WANG[yao_wx]
    dw_list = dw if isinstance(dw, list) else [dw]
    if day_branch in dw_list:
        score += 1.0; status.append("帝旺")

    # 季节休囚
    seasonal = _seasonal_status(month_branch)
    yao_season = seasonal.get(yao_wx)
    if yao_season in ["休", "囚", "死"]:
        score -= 1.5; status.append(f"休囚({yao_season})")

    # 入墓
    tomb = TOMB_BRANCH[yao_wx]
    tomb_list = tomb if isinstance(tomb, list) else [tomb]
    tomb_src = []
    if month_branch in tomb_list:
        tomb_src.append("月墓")
    if day_branch in tomb_list:
        tomb_src.append("日墓")
    if tomb_src:
        score = -0.1; status.append(f"入{'/'.join(tomb_src)}")

    # 绝地 / 化绝
    if not is_moving_yao and day_branch == EXTINCTION[yao_wx]:
        score -= 0.5; status.append("绝地")
    if changed_yao_branch and is_moving_yao and changed_yao_branch == EXTINCTION[yao_wx]:
        score -= 1.0; status.append("化绝")

    # 暗动
    if is_day_conflict and score >= 0:
        status.append("暗动")

    return {"score": round(score, 2), "status": status}


def _seasonal_status(month_branch: str) -> dict[str, str]:
    if month_branch in ["寅", "卯"]:
        return {"木": "旺", "火": "相", "水": "休", "金": "囚", "土": "死"}
    if month_branch in ["巳", "午"]:
        return {"火": "旺", "土": "相", "木": "休", "水": "囚", "金": "死"}
    if month_branch in ["申", "酉"]:
        return {"金": "旺", "水": "相", "土": "休", "火": "囚", "木": "死"}
    if month_branch in ["亥", "子"]:
        return {"水": "旺", "木": "相", "金": "休", "土": "囚", "火": "死"}
    return {"土": "旺", "金": "相", "火": "休", "木": "囚", "水": "死"}


# ----------------------------------------------------------------------
# 完整排盘
# ----------------------------------------------------------------------
def cast_chart(dt: datetime, *, birth_date: Any = None) -> dict[str, Any]:
    """完整六爻排盘（deterministic）。

    birth_date：本命信息（可选），用于提供更准确的月柱/日柱。
    """
    core = CalendarCore()

    # 用 CalendarCore 取四柱（第 6.1 节：所有术式共享同一历法内核）
    cal = core.compute(
        birth_date=birth_date or dt.date(),
        birth_time=f"{dt.hour:02d}:{dt.minute:02d}",
        target_date=dt.date(),
        target_time=f"{dt.hour:02d}:{dt.minute:02d}",
        gender="unknown",
    )
    if cal.degraded:
        # 降级：用简单基准日算法（仍确定性）
        year_branch = ZHI_ORDER[(dt.year - 1900) % 12]
        month_branch = _month_branch_simple(dt.month, dt.day)
        day_branch = ZHI_ORDER[((dt.date() - datetime(1900, 1, 1).date()).days) % 12]
        day_stem = GAN_ORDER[(6 + (dt.date() - datetime(1900, 1, 1).date()).days) % 10]
    else:
        month_gz = str(cal.payload.get("month_ganzhi", ""))
        day_gz = str(cal.payload.get("day_ganzhi", ""))
        hour_gz = str(cal.payload.get("hour_ganzhi", ""))
        year_branch = str(cal.payload.get("year_ganzhi", ""))[1:]
        month_branch = month_gz[1] if len(month_gz) > 1 else _month_branch_simple(dt.month, dt.day)
        day_stem = day_gz[0] if day_gz else ""
        day_branch = day_gz[1] if len(day_gz) > 1 else ""
        hour_branch = hour_gz[1] if len(hour_gz) > 1 else ZHI_ORDER[((dt.hour + 1) // 2) % 12]

    # 时间起卦（deterministic）
    lines = cast_by_time(dt, year_branch=year_branch, month=dt.month, day=dt.day,
                         hour_branch=hour_branch, minute=dt.minute)
    day_ganzhi = day_stem + day_branch
    xunkong = get_xunkong(day_ganzhi)
    liushou_order = get_liushou_order(day_branch)

    # 本卦
    ben = get_palace(lines)
    if ben is None:
        return {"error": "卦象无法识别", "lines": lines}

    palace = ben["palace"]
    palace_wx = PALACE_WUXING[palace]
    branches = HEXAGRAM_EARTHLY_BRANCH[palace]

    moving_idx = [i for i, x in enumerate(lines) if x in (3, 4)]
    changed = generate_changed(lines) if moving_idx else None
    bian = get_palace(changed) if changed else None
    changed_branches = HEXAGRAM_EARTHLY_BRANCH[bian["palace"]] if bian else None

    # 六亲 / 六神 / 旺衰逐爻
    yao_details = []
    for i in range(6):
        br = branches[i]
        wx = BRANCH_WUXING[br]
        liuqin = get_liuqin(palace_wx, wx)
        strength = calculate_yao_strength(
            yao_branch=br,
            month_branch=month_branch,
            day_branch=day_branch,
            changed_yao_branch=(changed_branches[i] if changed_branches else None),
            is_moving_yao=(i in moving_idx),
        )
        yao_details.append({
            "position": POSITIONS[i],
            "line": lines[i],
            "moving": i in moving_idx,
            "branch": br,
            "wuxing": wx,
            "liuqin": liuqin,
            "liushou": liushou_order[i],
            "is_shi": i == ben["shi"],
            "is_ying": i == ben["ying"],
            "score": strength["score"],
            "status": strength["status"],
            "changed_branch": changed_branches[i] if changed_branches else None,
        })

    # 缺失六亲
    present = {d["liuqin"] for d in yao_details}
    all_liuqin = ["父母", "兄弟", "子孙", "妻财", "官鬼"]
    defects = [x for x in all_liuqin if x not in present]

    return {
        "engine": ENGINE_VERSION,
        "cast_time": dt.isoformat(),
        "four_pillars": {
            "year": year_branch, "month": month_branch, "day": day_branch, "hour": hour_branch,
        },
        "day_ganzhi": day_ganzhi,
        "xunkong": xunkong,
        "ben_gua": {"palace": palace, "name": ben["name"], "type": ben["type"],
                    "lines": lines, "wuxing": palace_wx},
        "bian_gua": (
            {"palace": bian["palace"], "name": bian["name"], "type": bian["type"], "lines": changed}
            if bian else None
        ),
        "shi_yao_index": ben["shi"],
        "ying_yao_index": ben["ying"],
        "moving_yaos": [POSITIONS[i] for i in moving_idx],
        "yao_details": yao_details,
        "defects": defects,
        "input_hash": _input_hash(dt, birth_date),
    }


def _month_branch_simple(month: int, day: int) -> str:
    """简化月支（不精确，仅 CalendarCore 不可用时的兜底）。"""
    terms = [(2, 4), (3, 6), (4, 5), (5, 6), (6, 6), (7, 7),
             (8, 8), (9, 8), (10, 8), (11, 7), (12, 7), (1, 6)]
    if month == 1:
        return ZHI_ORDER[10] if day < 6 else ZHI_ORDER[11]
    for idx, (m, d) in enumerate(terms):
        if month == m and day >= d:
            return ZHI_ORDER[(idx + 1) % 12]
    return ZHI_ORDER[month - 2]


def _input_hash(dt: datetime, birth_date: Any) -> str:
    import hashlib
    return hashlib.sha256(
        f"liuyao:{dt.isoformat()}:{birth_date}".encode()
    ).hexdigest()
