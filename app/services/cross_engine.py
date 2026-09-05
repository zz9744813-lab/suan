"""多方法交叉引擎 —— 事件选择与叙事渲染的中枢。

对应工程方案：
- 第 12 节 Blind Multi-Agent（交叉只发生在「已计算完成的信号」层面）
- 第 55 节 数据来源分层（依据必须逐条可回溯到真实证据）
- 第 56 节 Event Ontology + narratives（描述来自确定性模板与证据）
- C-001 / C-005 / C-006：叙事不改变概率；概率权威仍在 Fusion/Null。

两条公开能力：

1. daily_almanac()：今日锦囊。完全由 lunar-python（老黄历）与确定性
   民俗规则派生：宜/忌、吉神方位、冲煞、彭祖百忌、吉时、五行幸运色数、
   本命桃花星当日是否引动。

2. rich_description()：把「Ontology 骨架 + 本窗口全部信号」渲染成
   「何时何事 / 可能形态 / 多法印证 / 建议 / 注意 / 幸运」的多行详批。

设计红线（对抗性自查）：
- 引擎只影响「选什么事、怎么说」，不影响「概率多少」（C-005）。
- 「交叉印证 N 法」是对信号事实的陈述，不是效力宣称（C-006）。
- 红鸾/天喜/咸池采用通行传统查表法，只输出「有无引动 + 所在」，
  不输出命定结论。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from sqlmodel import Session, select

from app.models.core import BirthProfile
from app.prediction.narratives import get_narrative
from app.schemas.signal import Signal, SourceType, TimeScale

# ----------------------------------------------------------------------
# 五行民俗映射（河图数 / 五色），传统术数参考
# ----------------------------------------------------------------------
ELEMENT_COLORS = {
    "木": ("青色/绿色", "碧色"),
    "火": ("红色/紫色", "橙色"),
    "土": ("黄色/咖色", "米色"),
    "金": ("白色/金色", "银色"),
    "水": ("黑色/蓝色", "灰色"),
}
# 河图数：一六水、二七火、三八木、四九金、五十土
ELEMENT_NUMBERS = {"水": (1, 6), "火": (2, 7), "木": (3, 8), "金": (4, 9), "土": (5, 0)}

TIANGAN = "甲乙丙丁戊己庚辛壬癸"
DIZHI = "子丑寅卯辰巳午未申酉戌亥"
_GAN_WUXING = ["木", "木", "火", "火", "土", "土", "金", "金", "水", "水"]
_ZHI_WUXING = ["水", "土", "木", "木", "土", "火", "火", "土", "金", "金", "土", "水"]

# 红鸾星：年支 → 红鸾所在地支（天喜 = 红鸾对宫）
HONGLUAN = {"子": "卯", "丑": "寅", "寅": "丑", "卯": "子", "辰": "亥", "巳": "戌",
            "午": "酉", "未": "申", "申": "未", "酉": "午", "戌": "巳", "亥": "辰"}
DUIGONG = {"子": "午", "丑": "未", "寅": "申", "卯": "酉", "辰": "戌", "巳": "亥",
           "午": "子", "未": "丑", "申": "寅", "酉": "卯", "戌": "辰", "亥": "巳"}

# 咸池（桃花）：年支或日支 → 桃花所在（寅午戌见卯 / 申子辰见酉 / 巳酉丑见午 / 亥卯未见子）
XIANCHI_GROUPS = [
    ({"寅", "午", "戌"}, "卯"),
    ({"申", "子", "辰"}, "酉"),
    ({"巳", "酉", "丑"}, "午"),
    ({"亥", "卯", "未"}, "子"),
]


def peach_blossom(branch: str) -> str:
    """年/日支 → 咸池桃花地支。"""
    for group, flower in XIANCHI_GROUPS:
        if branch in group:
            return flower
    return ""


def _gan_wuxing(gan: str) -> str:
    return _GAN_WUXING[TIANGAN.index(gan)] if gan in TIANGAN else ""


def _zhi_wuxing(zhi: str) -> str:
    return _ZHI_WUXING[DIZHI.index(zhi)] if zhi in DIZHI else ""


# ----------------------------------------------------------------------
# 今日锦囊
# ----------------------------------------------------------------------
def daily_almanac(
    session: Session, user_id: int, target_date: date
) -> dict[str, Any]:
    """今日锦囊：宜忌 / 吉神方位 / 冲煞 / 吉时 / 幸运色数 / 桃花引动。

    全部确定性计算；无出生档案时返回去掉个人化字段的通用版。
    """
    from lunar_python import Solar

    solar = Solar.fromYmd(target_date.year, target_date.month, target_date.day)
    lunar = solar.getLunar()

    day_gz = lunar.getDayInGanZhi()
    day_gan, day_zhi = day_gz[0], day_gz[1]
    day_wuxing = _gan_wuxing(day_gan)

    lucky_color = ELEMENT_COLORS.get(day_wuxing, ("", ""))
    lucky_numbers = ELEMENT_NUMBERS.get(day_wuxing, ())

    lucky_hours = [
        f"{t.getMinHm()[:5]} ~ {t.getMaxHm()[:5]}（{t.getGanZhi()}）"
        for t in lunar.getTimes()
        if t.getTianShenLuck() == "吉"
    ][:4]

    out: dict[str, Any] = {
        "date": target_date.isoformat(),
        "day_ganzhi": day_gz,
        "day_wuxing": day_wuxing,
        "lunar_date": f"农历{lunar.getMonthInChinese()}月{lunar.getDayInChinese()}",
        "yi": list(lunar.getDayYi())[:6],
        "ji": list(lunar.getDayJi())[:6],
        "xi_dir": lunar.getDayPositionXiDesc(),
        "cai_dir": lunar.getDayPositionCaiDesc(),
        "fu_dir": lunar.getDayPositionFuDesc(),
        "chong": lunar.getDayChongDesc(),
        "sha_direction": lunar.getDaySha(),
        "day_god": f"{lunar.getDayTianShen()}（{lunar.getDayTianShenType()}）",
        "pengzu": [lunar.getPengZuGan(), lunar.getPengZuZhi()],
        "lucky_hours": lucky_hours,
        "lucky_color": lucky_color[0],
        "lucky_color_aux": lucky_color[1],
        "lucky_numbers": list(lucky_numbers),
        "day_zhi": day_zhi,
    }

    # ---------- 日卦（周易经文参读，通用版/个人版均带） ----------
    # 确定性日粒度时间起卦：上卦=(年支序+月+日)%8，下卦再加日支序，
    # 动爻同源取模（复用梅花引擎，与预测盘同一套已验证卦名表）。
    # 经文是文献参读，非效力宣称（C-006）。
    try:
        from datetime import datetime as _dt, time as _time

        from app.core.meihua.engine import cast_hexagram as _cast_hexagram
        from app.core.zhouyi import by_name as _gua_by_name, cite as _gua_cite

        gua = _cast_hexagram(
            _dt.combine(target_date, _time(12, 0)),
            year_branch=lunar.getYearInGanZhi()[1],
            hour_branch=day_zhi,
        )
        ben_name = gua["ben_gua"]["name"]
        canon = _gua_by_name(ben_name) or {}
        out["daily_gua"] = {
            "name": ben_name,
            "short": canon.get("short", ""),
            "lines": list(gua["ben_gua"]["lines"]),  # 初→上，1 阳 0 阴（供前端画卦象）
            "moving_yao": gua["moving_yao"],
            "gua_ci": _gua_cite(ben_name),
            "yao_ci": _gua_cite(ben_name, gua["moving_yao"]),
            "xiang": canon.get("xiang", ""),
        }
    except Exception as exc:  # 经文缺失不阻断锦囊
        import logging

        logging.getLogger(__name__).warning("日卦生成失败：%s", exc)

    # ---------- 个人化层（需出生档案）----------
    profile = session.exec(
        select(BirthProfile).where(BirthProfile.user_id == user_id)
    ).first()
    if profile is None:
        return out

    birth_lunar = Solar.fromYmd(
        profile.solar_birth_date.year,
        profile.solar_birth_date.month,
        profile.solar_birth_date.day,
    ).getLunar()
    year_zhi = birth_lunar.getYearInGanZhi()[1]
    bazi_day_gz = birth_lunar.getDayInGanZhi()
    day_master = bazi_day_gz[0]
    day_master_wx = _gan_wuxing(day_master)

    # 日主 × 当日天干 → 十神关系一句话（与 bazi adapter 同一套简化分类）
    from app.core.bazi.adapter import shishen_category

    relation = shishen_category(day_master, day_gan)

    # 桃花引动：红鸾 / 天喜 / 咸池 今日是否被日支引动
    hongluan = HONGLUAN.get(year_zhi, "")
    tianxi = DUIGONG.get(hongluan, "")
    xianchi_year = peach_blossom(year_zhi)
    xianchi_day = peach_blossom(bazi_day_gz[1])

    activated: list[str] = []
    if day_zhi == hongluan:
        activated.append(f"红鸾星动（{hongluan}）")
    if day_zhi == tianxi:
        activated.append(f"天喜星动（{tianxi}）")
    if day_zhi == xianchi_year or day_zhi == xianchi_day:
        activated.append(f"咸池引动（{day_zhi}）")

    # 冲日支：当日支冲本命日支
    clash_day = DUIGONG.get(day_zhi) == bazi_day_gz[1]

    out.update(
        {
            "day_master": day_master,
            "day_master_wuxing": day_master_wx,
            "day_master_relation": relation,
            "peach_blossom_stars": {
                "hongluan": hongluan,
                "tianxi": tianxi,
                "xianchi": sorted({xianchi_year, xianchi_day} - {""}),
            },
            "peach_activated": activated,
            "clash_birth_day": clash_day,
        }
    )
    return out


# ----------------------------------------------------------------------
# 交叉印证（从已收集的信号汇总）
# ----------------------------------------------------------------------
@dataclass
class CrossSummary:
    """一次候选的交叉印证摘要。"""

    supporting: dict[str, list[str]] = field(default_factory=dict)   # 源 → 依据句
    opposing: dict[str, list[str]] = field(default_factory=dict)
    metaphysical_support: int = 0   # 正向术式源数
    metaphysical_oppose: int = 0

    @property
    def crossed(self) -> bool:
        """「多方法交叉」达成标准：≥2 个术式源同向支持。"""
        return self.metaphysical_support >= 2


SOURCE_LABEL = {
    SourceType.ZIWEI: "紫微",
    SourceType.BAZI: "八字",
    SourceType.QIMEN: "奇门",
    SourceType.LIUYAO: "六爻",
    SourceType.MEIHUA: "梅花",
    SourceType.PALM: "掌纹",
    SourceType.FACE: "面相",
    SourceType.REALITY: "现实",
    SourceType.NULL: "基线",
}


def summarize_signals(signals: list[Signal]) -> CrossSummary:
    """把一次候选的信号汇总成交叉印证摘要（只陈述事实）。"""
    s = CrossSummary()
    for sig in signals:
        if sig.degraded or sig.source in (SourceType.NULL, SourceType.REALITY):
            continue
        label = SOURCE_LABEL.get(sig.source, sig.source.value)
        # 每个源取第一条主证据展示（其余在详情页可见）
        ev_text = sig.evidence[0].description if sig.evidence else ""
        if sig.direction > 0:
            s.supporting.setdefault(label, []).append(ev_text)
            s.metaphysical_support += 1
        elif sig.direction < 0:
            s.opposing.setdefault(label, []).append(ev_text)
            s.metaphysical_oppose += 1
    return s


# ----------------------------------------------------------------------
# 富文本描述构建
# ----------------------------------------------------------------------
_WEEKDAY_ZH = "一二三四五六日"

# 窗口文案 → 用户友好句式
def when_text(scale: TimeScale, start, end) -> str:
    wd = f"周{_WEEKDAY_ZH[start.weekday()]}"
    if scale == TimeScale.DAY:
        return f"{start.month}月{start.day}日（{wd}）"
    if scale == TimeScale.WEEK:
        return f"{start.month}月{start.day}日 ~ {end.month}月{end.day}日这一周"
    if scale == TimeScale.MONTH:
        return f"{start.year}年{start.month}月"
    return f"{start.year}年"


def rich_description(
    *,
    event_type: str,
    label: str,
    scale: TimeScale,
    window_start,
    window_end,
    signals: list[Signal],
    almanac: dict[str, Any] | None,
    include_claim: bool = True,
    probability: float | None = None,
    null_probability: float | None = None,
) -> str:
    """把候选渲染成多行详批（确定性，秒出，无 LLM）。"""
    when = when_text(scale, window_start, window_end)
    narrative = get_narrative(event_type)
    cross = summarize_signals(signals)

    lines: list[str] = []
    if include_claim:
        lines.append(f"{when}{label}。")

    # 可能形态（最多取 3）
    scenarios = narrative.scenarios[:3]
    if scenarios:
        lines.append("常见情景：" + "；".join(scenarios) + "。")

    # 全法盘点：同一时间点五术同参，✓/✗/○ 全量呈现（含未表态者）——
    # 交叉印证不只看「支持了什么」，也要看「谁没说话/谁反对」（对抗性要求）。
    # 掌纹/面相属影像术式（需拍照），有信号时一并入盘点，无则注明未参校。
    label_of = SOURCE_LABEL
    _engine_labels = ["八字", "紫微", "六爻", "梅花", "奇门"]
    _image_labels = ["掌纹", "面相"]

    def _mark(sigs: list[Signal]) -> str:
        live = [s for s in sigs if not s.degraded]
        up = any(s.direction > 0 for s in live)
        down = any(s.direction < 0 for s in live)
        if up and down:
            return "✓/✗ 分歧"
        if up:
            return "✓ 同向"
        if down:
            return "✗ 反向"
        return "○ 未表态"

    tally: list[str] = []
    for lbl in _engine_labels:
        tally.append(f"{lbl}{_mark([s for s in signals if label_of.get(s.source) == lbl])}")
    has_image_signal = False
    for lbl in _image_labels:
        img_sigs = [s for s in signals if label_of.get(s.source) == lbl]
        if img_sigs:
            has_image_signal = True
            tally.append(f"{lbl}{_mark(img_sigs)}")
    lines.append(
        "全法盘点（同一时间点·五术同参）："
        + " ".join(tally)
        + ("" if has_image_signal else "（掌纹/面相需拍照参校，未计入）")
        + "。"
    )

    # 多法印证（真实证据来源分层展示）
    basis: list[str] = []
    for src, evs in cross.supporting.items():
        joined = "；".join(e for e in evs if e)
        basis.append(f"✓ {src}：{joined}" if joined else f"✓ {src}：信号同向")
    for src, evs in cross.opposing.items():
        joined = "；".join(e for e in evs if e)
        basis.append(f"✗ {src}：{joined}" if joined else f"✗ {src}：信号反向")
    if basis:
        head = (
            f"多法印证（{cross.metaphysical_support} 法同向"
            + (f"，{cross.metaphysical_oppose} 法示警" if cross.metaphysical_oppose else "")
            + "）："
            if cross.metaphysical_support or cross.metaphysical_oppose
            else ""
        )
        lines.append(head + " / ".join(basis))
    else:
        lines.append("多法印证：本轮各术式无明显同向信号，按基线概率留样验证。")

    # 经文献录：本轮信号附带的周易经文出处（文献参读，非效力宣称，C-006）
    canon_seen: list[str] = []
    for sig in signals:
        for ev in sig.evidence or []:
            d = getattr(ev, "description", "") or ""
            if "《周易·" in d:
                frag = d.split("：", 1)[1].strip() if "：" in d else d.strip()
                if frag and frag not in canon_seen:
                    canon_seen.append(frag)
    if canon_seen:
        show = canon_seen[:2]
        tail = f"（共 {len(canon_seen)} 条，其余见信号证据）" if len(canon_seen) > 2 else ""
        body = ("；".join(show) + tail).rstrip("。")
        lines.append("经文献录（文献参读，非效力宣称）：" + body + "。")

    # 姻缘事件且当日情缘星引动 → 显式点出（用户高频关心的「缘分何时」）
    if almanac and event_type.startswith("relationship."):
        peach = almanac.get("peach_activated") or []
        if peach:
            lines.append(f"情缘提示：当日起算日引动本命{'、'.join(peach)}，宜主动社交。")

    # 概率口径：与「何时何事」断言同等地位地陈述证据强度（C-006）。
    # 断言可以是强命题，但数字必须同步摆出 —— 信号没抬高概率时直说持平，
    # 不允许「读上去板上钉钉、数字上毫无增量」的割裂感。
    if probability is not None and null_probability is not None:
        diff = probability - null_probability
        p_pct, n_pct = round(probability * 100), round(null_probability * 100)
        if abs(diff) < 0.005:
            lines.append(
                f"概率口径：本轮信号未明显抬高发生概率（{p_pct}%，与基线 {n_pct}% 持平），"
                "按平常心对待即可。"
            )
        elif diff > 0:
            lines.append(
                f"概率口径：信号将概率由基线 {n_pct}% 抬至 {p_pct}%"
                f"（+{round(diff * 100)} 个百分点）。"
            )
        else:
            lines.append(
                f"概率口径：信号评估（{p_pct}%）低于日常基线（{n_pct}%），以基线为准。"
            )

    lines.append("建议：" + narrative.advice)
    # 注意项无条件展示：caution 是务实防错，不是凶断；无反向信号时也不缺席，
    # 避免「全篇只有好话」的单侧观感。
    oppose_names = "、".join(cross.opposing.keys())
    head = f"注意（{oppose_names} 示警）" if oppose_names else "注意"
    lines.append(f"{head}：{narrative.caution}")

    # 幸运元素（窗口起始日的五行锦囊）
    if almanac:
        luck_bits = []
        if almanac.get("lucky_color"):
            luck_bits.append(f"色宜 {almanac['lucky_color']}")
        if almanac.get("lucky_numbers"):
            luck_bits.append("数宜 " + "、".join(str(n) for n in almanac["lucky_numbers"]))
        if almanac.get("cai_dir"):
            luck_bits.append(f"财神位 {almanac['cai_dir']}")
        if luck_bits:
            lines.append("幸运参考（传统民俗，仅供参考）：" + "；".join(luck_bits) + "。")

    return "\n".join(lines)


# ----------------------------------------------------------------------
# 读取端叙事重建
# ----------------------------------------------------------------------
def signals_from_rows(rows: list[Any]) -> list[Signal]:
    """SignalRecord 行 → Signal 对象（与冻结落库时一致的字段映射）。

    叙事是确定性的展示层：只要输入（事件 + 信号 + 日期）相同，
    每次重建都逐字相同 —— 不写库、不进冻结哈希、C-003 语义不破。
    """
    from app.schemas.signal import Evidence

    return [
        Signal(
            signal_id=s.signal_id,
            source=s.source_type,
            domain=s.domain,
            target_event=s.target_event,
            direction=s.direction,
            strength=s.strength,
            confidence=s.confidence,
            time_window={"start": s.window_start, "end": s.window_end},
            time_scale=TimeScale(s.time_scale),
            rule_ids=s.rule_ids,
            dependency_group=s.dependency_group,
            engine_version=s.engine_version,
            degraded=s.degraded,
            degrade_reason=s.degrade_reason,
            evidence=[Evidence(**e) for e in (s.evidence or []) if isinstance(e, dict)],
        )
        for s in rows
    ]


def narrative_for_record(session: Session, record: Any, signal_rows: list[Any]) -> str:
    """为一条已冻结的预测重建展示层详批（deterministic）。"""
    from app.prediction.ontology import ONTOLOGY

    scale = TimeScale(record.time_scale)
    spec = ONTOLOGY.get(record.event_type)
    label = spec.label if spec else record.event_type
    try:
        almanac = daily_almanac(session, int(record.user_id), record.window_start.date())
    except Exception:
        almanac = None
    return rich_description(
        event_type=record.event_type,
        label=label,
        scale=scale,
        window_start=record.window_start,
        window_end=record.window_end,
        signals=signals_from_rows(signal_rows),
        almanac=almanac,
        include_claim=False,  # 卡片标题行已有断言本体，不重复
        probability=record.probability,
        null_probability=record.null_probability,
    )
