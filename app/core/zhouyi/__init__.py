"""周易经文库 —— 64 卦卦辞 / 大象传 / 384 爻辞 + 乾坤用辞。

定位（宪法 C-006 / 第 9 节）：
- 这里是**古典文献的数字化抄本**（通行本《周易》），供六爻/梅花信号
  附上「经文出处」，让断语可追溯回经典原文；
- 经文是**参考文本，不是效力宣称**——系统不主张其预测效力，
  有效性一律交给系统自己的长期验证闭环；
- 经文属于「读侧叙事素材」：只进 Signal.evidence / 叙事层，
  **绝不进冻结描述**（对抗 Gate 审的文本域），见 HANDOFF 坑 16。

数据以卦名为主键；阴阳串（初→上）→ 卦名 的映射复用六爻引擎的
HEXAGRAMS 表（单一事实源，测试里有逐卦对照防漂移）。
"""

from __future__ import annotations

from typing import Any

from .texts import TEXTS


def _name_to_pattern() -> dict[str, str]:
    """卦名 → 阴阳串（懒加载，避免与六爻引擎循环导入）。"""
    from app.core.liuyao.engine import HEXAGRAMS

    return {v["name"]: k for k, v in HEXAGRAMS.items()}


def yao_positions(name: str) -> list[str] | None:
    """六爻爻题（如 乾 → 初九/九二/…/上九），按阴阳推导。

    爻题规则：初/上位用「初九/上九」式，二至五位用「九二/九三」式。
    """
    pat = _name_to_pattern().get(name)
    if pat is None:
        return None
    lines = [int(x) for x in pat.split(",")]
    yang = ["初九", "九二", "九三", "九四", "九五", "上九"]
    yin = ["初六", "六二", "六三", "六四", "六五", "上六"]
    return [yang[i] if lines[i] else yin[i] for i in range(6)]


def by_pattern(pattern: str) -> dict[str, Any] | None:
    """按阴阳串（初→上，逗号分隔）查经文。"""
    name = name_for_pattern(pattern)
    return TEXTS.get(name) if name else None


def name_for_pattern(pattern: str) -> str | None:
    from app.core.liuyao.engine import HEXAGRAMS

    e = HEXAGRAMS.get(pattern)
    return e["name"] if e else None


def by_lines(lines: list[int]) -> dict[str, Any] | None:
    """按六爻列表（初→上，1 阳 0 阴）查经文。"""
    if len(lines) != 6:
        return None
    return by_pattern(",".join(str(x) for x in lines))


def by_name(name: str) -> dict[str, Any] | None:
    """按卦名（如「乾为天」）查经文。"""
    return TEXTS.get(name)


def gua_ci(name: str) -> str | None:
    """卦辞原文。"""
    e = by_name(name)
    return e["gua"] if e else None


def yao_ci(name: str, yao_index: int) -> str | None:
    """动爻爻辞原文。yao_index 从 1 起（初爻=1）。"""
    e = by_name(name)
    if e is None or not (1 <= yao_index <= 6):
        return None
    return e["yao"][yao_index - 1]


def cite(name: str, yao_index: int | None = None) -> str | None:
    """格式化引文（叙事层直接可用）：「《周易·乾》元亨利贞。」"""
    e = by_name(name)
    if e is None:
        return None
    short = e["short"]
    if yao_index is None:
        return f"《周易·{short}》{e['gua']}"
    pos = yao_positions(name)
    if pos is None or not (1 <= yao_index <= 6):
        return None
    return f"《周易·{short}》{pos[yao_index - 1]}：{e['yao'][yao_index - 1]}"
