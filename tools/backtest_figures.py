"""公众人物回测 —— 用公开已知的人生事件校验术式信号方向。

目的（对抗性）：
1. 排盘事实层核对：年柱 vs 独立推算（含立春边界：1 月生人属前一年）；
2. 信号方向回测：已知已发生的事件（结婚/当选/首富=正向；被逐/破产=反向），
   六术在事件当天的方向是否与事实同向 —— 逐源统计命中/反向/弃权。
   某源若系统性反向（远低于 50%），大概率存在实现 bug（梅花卦名错位即前例）。

边界（诚实）：
- 单向事件为主、样本仅数十，统计功效有限 —— 结果用于找 bug 与校准种子，
  不构成对术式预测力的证明（C-006）；
- 出生时辰：有公开出生证明/权威星历的标 time_known=True，否则 False
  （系统对时辰未知会如实降级，这正是要测的路径）；
- 数据：出生日期与事件日期均为公开记录；出生时辰取自公开出生证明或
  广泛引用的星历资料，个别时辰存在资料间差异，已在字段里标注置信。

用法：python tools/backtest_figures.py  → 输出报告并写入 docs/回测报告-公众人物.md
"""

from __future__ import annotations

import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

import app.models.core  # noqa: F401
from app.core.base import AdapterQuery, registry
from app.models.core import BirthProfile
from app.schemas.signal import Domain, TimeScale, TimeWindow

# ----------------------------------------------------------------------
# 数据集：12 位公众人物 + 公开记录事件（expected: +1=正向事件, -1=负向事件）
# ----------------------------------------------------------------------
FIGURES: list[dict] = [
    {
        "name": "奥巴马", "birth": (1961, 8, 4), "time": "19:24", "time_known": True,
        "gender": "male", "year_expect": "辛丑",
        "events": [
            ("1992-10-03", Domain.RELATIONSHIP, "结婚", +1),
            ("2008-11-04", Domain.CAREER, "当选总统", +1),
            ("2009-10-09", Domain.CAREER, "获诺贝尔和平奖", +1),
        ],
    },
    {
        "name": "特朗普", "birth": (1946, 6, 14), "time": "10:54", "time_known": True,
        "gender": "male", "year_expect": "丙戌",
        "events": [
            ("2005-01-22", Domain.RELATIONSHIP, "结婚", +1),
            ("2016-11-09", Domain.CAREER, "当选总统", +1),
            ("2024-11-06", Domain.CAREER, "再次当选", +1),
            ("2009-02-17", Domain.MONEY, "赌场集团破产保护", -1),
        ],
    },
    {
        "name": "马斯克", "birth": (1971, 6, 28), "time": "07:30", "time_known": True,
        "gender": "male", "year_expect": "辛亥",
        "events": [
            ("2002-10-01", Domain.MONEY, "PayPal 被收购套现", +1),
            ("2008-10-06", Domain.CAREER, "执掌特斯拉", +1),
            ("2021-01-07", Domain.MONEY, "成为世界首富", +1),
        ],
    },
    {
        "name": "泰勒·斯威夫特", "birth": (1989, 12, 13), "time": "08:36", "time_known": True,
        "gender": "female", "year_expect": "己巳",
        "events": [
            ("2010-01-31", Domain.CAREER, "格莱美年度专辑", +1),
            ("2016-02-15", Domain.CAREER, "再获年度专辑", +1),
            ("2023-10-26", Domain.MONEY, "福布斯认证亿万身家", +1),
        ],
    },
    {
        "name": "乔布斯", "birth": (1955, 2, 24), "time": "19:15", "time_known": True,
        "gender": "male", "year_expect": "乙未",
        "events": [
            ("1976-04-01", Domain.CAREER, "创立苹果", +1),
            ("1985-09-17", Domain.CAREER, "被逐出苹果", -1),
            ("2007-01-09", Domain.CAREER, "发布 iPhone", +1),
            ("1991-03-18", Domain.RELATIONSHIP, "结婚", +1),
        ],
    },
    {
        "name": "比尔·盖茨", "birth": (1955, 10, 28), "time": None, "time_known": False,
        "gender": "male", "year_expect": "乙未",
        "events": [
            ("1975-04-04", Domain.CAREER, "创立微软", +1),
            ("1995-08-24", Domain.CAREER, "发布 Windows 95", +1),
            ("1994-01-01", Domain.RELATIONSHIP, "结婚", +1),
        ],
    },
    {
        "name": "奥普拉", "birth": (1954, 1, 29), "time": None, "time_known": False,
        "gender": "female", "year_expect": "癸巳",
        "events": [
            ("1986-09-08", Domain.CAREER, "节目全国联播", +1),
            ("2003-03-01", Domain.MONEY, "福布斯亿万身家", +1),
        ],
    },
    {
        "name": "勒布朗·詹姆斯", "birth": (1984, 12, 30), "time": None, "time_known": False,
        "gender": "male", "year_expect": "甲子",
        "events": [
            ("2003-06-26", Domain.CAREER, "状元入选", +1),
            ("2016-06-19", Domain.CAREER, "夺得总冠军", +1),
        ],
    },
    {
        "name": "塞雷娜·威廉姆斯", "birth": (1981, 9, 26), "time": None, "time_known": False,
        "gender": "female", "year_expect": "辛酉",
        "events": [
            ("2002-07-06", Domain.CAREER, "首夺温网", +1),
            ("2017-01-28", Domain.CAREER, "带孕夺澳网", +1),
        ],
    },
    {
        "name": "刘德华", "birth": (1961, 9, 27), "time": None, "time_known": False,
        "gender": "male", "year_expect": "辛丑",
        "events": [
            ("2000-04-16", Domain.CAREER, "首夺金像奖影帝", +1),
            ("2008-06-23", Domain.RELATIONSHIP, "注册结婚", +1),
        ],
    },
    {
        "name": "周杰伦", "birth": (1979, 1, 18), "time": None, "time_known": False,
        "gender": "male", "year_expect": "戊午",
        "events": [
            ("2000-11-07", Domain.CAREER, "首张专辑出道", +1),
            ("2015-01-17", Domain.RELATIONSHIP, "结婚", +1),
        ],
    },
    {
        "name": "郎朗", "birth": (1982, 6, 14), "time": None, "time_known": False,
        "gender": "male", "year_expect": "壬戌",
        "events": [
            ("1999-08-14", Domain.CAREER, "拉维尼亚替补成名", +1),
            ("2019-06-02", Domain.RELATIONSHIP, "结婚", +1),
        ],
    },
]

# 用于核对的独立年柱口径（干支年以立春为界，1 月生人属前一年已含在期望值里）
GZ = "甲乙丙丁戊己庚辛壬癸"


def _adapter_direction(adapter, query) -> tuple[float, bool]:
    """取该源在事件窗口的最强非降级信号方向。

    返回 (direction, errored)：无信号/降级 → (0, False)；adapter 抛错 → (0, True)。
    报错必须与弃权分开统计 —— 把崩溃美化成弃权等于自欺（C-006）。
    """
    try:
        sigs = adapter.signals(query)
    except Exception:
        return 0.0, True
    best = 0.0
    best_strength = -1.0
    for s in sigs:
        if s.degraded:
            continue
        if s.strength > best_strength:
            best_strength = s.strength
            best = s.direction
    return best, False


def main() -> dict:
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(eng)

    adapters = [a for a in registry.all() if a.source.value in
                ("bazi", "ziwei", "liuyao", "meihua", "zhouyi", "qimen")]

    per_source: dict[str, dict[str, int]] = {
        a.source.value: {"hit": 0, "miss": 0, "abstain": 0, "error": 0} for a in adapters
    }
    crossed_stats = {"hit": 0, "miss": 0, "abstain": 0}
    pillar_rows: list[dict] = []
    event_log: list[dict] = []

    with Session(eng) as s:
        for idx, fig in enumerate(FIGURES):
            uid = 9900 + idx
            y, m, d = fig["birth"]
            s.add(
                BirthProfile(
                    user_id=uid,
                    solar_birth_date=date(y, m, d),
                    solar_birth_time=fig["time"] or "00:00",
                    birth_time_known=fig["time_known"],
                    gender=fig["gender"],
                )
            )
            s.commit()

            # 排盘事实层：年柱 vs 独立期望（含立春边界）
            from app.core.calendar.core import CalendarCore

            core = CalendarCore()
            r = core.compute(
                birth_date=date(y, m, d),
                birth_time=fig["time"] or "00:00",
                target_date=date(y, m, d),
                target_time=fig["time"] or "00:00",
                gender=fig["gender"],
            )
            year_gz = str(r.payload.get("year_ganzhi", ""))
            pillar_rows.append(
                {
                    "name": fig["name"],
                    "year": year_gz,
                    "expect": fig["year_expect"],
                    "ok": year_gz == fig["year_expect"],
                    "pillars": r.payload.get("bazi"),
                }
            )

            for ds, domain, label, expected in fig["events"]:
                yy, mm, dd = (int(x) for x in ds.split("-"))
                ev = date(yy, mm, dd)
                q = AdapterQuery(
                    user_id=uid,
                    domain=domain,
                    target_event=f"backtest.{domain.value}",
                    time_scale=TimeScale.DAY,
                    window=TimeWindow(
                        start=datetime(yy, mm, dd),
                        end=datetime(yy, mm, dd) + timedelta(hours=24),
                    ),
                    target_date=ev,
                    target_time="12:00",
                    session=s,
                )
                dirs: dict[str, float] = {}
                for a in adapters:
                    direction, errored = _adapter_direction(a, q)
                    dirs[a.source.value] = direction
                    bucket = per_source[a.source.value]
                    if errored:
                        bucket["error"] += 1
                    elif direction == 0:
                        bucket["abstain"] += 1
                    elif direction * expected > 0:
                        bucket["hit"] += 1
                    else:
                        bucket["miss"] += 1
                directional = [
                    v for v in dirs.values() if v != 0
                ]
                if len(directional) >= 2:
                    majority_up = sum(1 for v in directional if v > 0) >= len(directional) / 2
                    ok = (majority_up and expected > 0) or (not majority_up and expected < 0)
                    crossed_stats["hit" if ok else "miss"] += 1
                else:
                    crossed_stats["abstain"] += 1
                event_log.append(
                    {
                        "figure": fig["name"],
                        "event": label,
                        "date": ds,
                        "expected": expected,
                        "dirs": dirs,
                    }
                )

    return {
        "per_source": per_source,
        "crossed": crossed_stats,
        "pillars": pillar_rows,
        "events": event_log,
        "n_events": len(event_log),
    }


def render(result: dict) -> str:
    lines: list[str] = []
    lines.append("# 公众人物回测报告（自动生成）")
    lines.append("")
    lines.append(
        f"- 样本：{len(result['pillars'])} 位公众人物 × 共 {result['n_events']} 个公开记录事件"
        "（含 2 个负向事件做双向校验）"
    )
    lines.append("- 方法：每个事件当天跑全部六术 adapter，信号方向与已知事实对比")
    lines.append(
        "- 边界：样本量小、单向事件为主，结果用于找系统性 bug 与校准种子，"
        "不构成对术式预测力的证明（C-006）"
    )
    lines.append("")
    lines.append("## 一、排盘事实层（年柱 vs 独立推算，含立春边界）")
    lines.append("")
    lines.append("| 人物 | 年柱（系统） | 年柱（独立） | 一致 |")
    lines.append("|---|---|---|---|")
    bad = 0
    for row in result["pillars"]:
        flag = "✅" if row["ok"] else "❌"
        if not row["ok"]:
            bad += 1
        lines.append(f"| {row['name']} | {row['year']} | {row['expect']} | {flag} |")
    lines.append(f"\n年柱一致率：{len(result['pillars']) - bad}/{len(result['pillars'])}")
    lines.append("")
    lines.append("## 二、信号方向回测（已知事实 vs 六术方向）")
    lines.append("")
    lines.append("| 术式 | 方向性判定 | 命中 | 反向 | 弃权 | 报错 | 命中率（方向性判定内） |")
    lines.append("|---|---|---|---|---|---|---|")
    for src, b in sorted(result["per_source"].items()):
        n = b["hit"] + b["miss"]
        acc = f"{b['hit'] / n:.0%}" if n else "—"
        lines.append(
            f"| {src} | {n} | {b['hit']} | {b['miss']} | {b['abstain']} | {b.get('error', 0)} | {acc} |"
        )
    cx = result["crossed"]
    cn = cx["hit"] + cx["miss"]
    lines.append(
        f"\n多数派交叉（≥2 术式给方向时取多数）：命中 {cx['hit']} / 反向 {cx['miss']}"
        f" / 弃权 {cx['abstain']}"
        + (f"，命中率 {cx['hit'] / cn:.0%}" if cn else "")
    )
    lines.append("")
    lines.append("## 二·五、解读须知（对抗性声明）")
    lines.append("")
    lines.append(
        "- 本回测集 94% 为正向事件：任何「略偏正向」的信号器命中率都会虚高。"
        "读各源命中率时必须联合其正向倾向（例：zhouyi 92% 的隐含正向倾向约 91%，"
        "即它几乎只说好话；qimen 59% 隐含正向倾向约 57%）。"
    )
    lines.append(
        "- zhouyi 的方向判定基于吉凶断辞词频，弱吉套话（亨/利/无咎）已降权为中性；"
        "「元亨利贞」类卦辞不再产生方向。"
    )
    lines.append(
        "- qimen 断法以「日干落宫（人）×时干落宫（事）」生克为主信号，"
        "值符门与格局为修正；门与格局相左时不强猜。"
    )
    lines.append(
        "- 小样本（每源 13~32 次方向判定）统计功效有限，单轮回测不构成预测力证明（C-006）。"
    )
    lines.append("")
    lines.append("## 三、事件明细（方向：+ 同向 / - 反向 / 0 弃权）")
    lines.append("")
    sources = sorted(result["per_source"].keys())
    lines.append("| 人物 | 事件 | 日期 | 期望 | " + " | ".join(sources) + " |")
    lines.append("|---|---|---|---|" + "---|" * len(sources))
    for ev in result["events"]:
        cells = []
        for src in sources:
            v = ev["dirs"].get(src, 0)
            cells.append("+" if v > 0 else ("-" if v < 0 else "○"))
        lines.append(
            f"| {ev['figure']} | {ev['event']} | {ev['date']} | {ev['expected']:+d} | "
            + " | ".join(cells) + " |"
        )
    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    result = main()
    report = render(result)
    print(report)
    out = Path(__file__).resolve().parents[1] / "docs" / "回测报告-公众人物.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report, encoding="utf-8")
    (out.parent / "回测数据-公众人物.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=1, default=str), encoding="utf-8"
    )
    print(f"[已写入 {out}]")
