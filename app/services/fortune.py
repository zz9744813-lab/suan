"""命理批示服务（本命盘解读 + 大运 / 流年运势）。

定位（与预测闭环严格区分）：
    预测闭环 = 可证伪事件 + 冻结 + 现实验证 + 评分（系统的灵魂，第 2 节）。
    命理批示 = 传统术数对「命盘」的解读展示，属于传统术数内容本身，
              不进入 Fusion、不参与评分，纯展示。

硬性约束（第 6.1 / 65 节）：
    - 程序负责排盘，LLM 不允许自己算命盘。
    - 批示是「传统术数参考」，不是科学验证的预知，不得诊断疾病 / 预测死亡日期 /
      替代医疗、法律、财务专业判断。
    - 盘面输入必须精简（qiyovo 中转站长 prompt 会挂起）。

LLM 不可用时：返回确定性排盘骨架（八字/大运/流年事实），不含批示文本，
由前端降级展示。
"""

from __future__ import annotations

import hashlib
import json
from datetime import date
from typing import Any

from sqlmodel import Session, select

from app.core.calendar.core import CalendarCore
from app.models.core import BirthProfile
from app.models.metaphysical import FortuneReading


# 未来流年展示跨度（默认 10 年）
FUTURE_YEARS = 10


def _zodiac(year_ganzhi: str) -> str:
    """年干支 → 生肖。"""
    dizhi = "子丑寅卯辰巳午未申酉戌亥"
    animals = "鼠牛虎兔龙蛇马羊猴鸡狗猪"
    if not year_ganzhi or len(year_ganzhi) < 2:
        return ""
    dz = year_ganzhi[1]
    idx = dizhi.find(dz)
    return animals[idx] if idx >= 0 else ""


def future_liunian(
    start_year: int,
    n: int = FUTURE_YEARS,
    birth_year: int | None = None,
    birth_month: int = 1,
    birth_day: int = 1,
) -> list[dict[str, Any]]:
    """未来 n 年的流年干支 + 生肖 + 精确周岁（确定性，取自 lunar-python）。

    取年中（6 月 15 日）避开立春边界，保证年柱准确。
    年龄：对每个流年，用"流年那年的生日同月同日"作为参考点算精确周岁：
        年龄 = 流年年 - 出生年
        若流年当年 (月, 日) 还未到生日 (月, 日)，再 -1
        （不直接用 today，因为要看"流年那一年你多大了"）
    """
    from lunar_python import Solar

    out: list[dict[str, Any]] = []
    for y in range(start_year, start_year + n):
        lunar = Solar.fromYmd(y, 6, 15).getLunar()
        gz = lunar.getYearInGanZhi()
        age = None
        if birth_year is not None:
            age = y - birth_year
            # 流年那年的生日是否已过（用年中 6-15 作为参考，6-15 < 12-20 则 -1）
            if (6, 15) < (birth_month, birth_day):
                age -= 1
        out.append(
            {
                "year": y,
                "ganzhi": gz,
                "zodiac": lunar.getYearShengXiao(),
                "age": age,
            }
        )
    return out


def _profile_hash(profile: BirthProfile) -> str:
    """出生档案指纹：档案关键字段不变则批示不变。

    任一字段变化（生日/时辰/性别/出生地/真太阳时/时辰是否已知）都会改变 hash，
    从而触发批示重算。流年/大运随时间自然推移，但排盘在 build_chart_summary 里
    用 date.today() 实时算，缓存只存"某次快照"，命中即返回快照即可。
    """
    key = {
        "date": str(profile.solar_birth_date),
        "time": profile.solar_birth_time,
        "known": profile.birth_time_known,
        "gender": profile.gender,
        "place": profile.birth_place,
        "lng": profile.longitude,
        "lat": profile.latitude,
        "true_solar": profile.use_true_solar_time,
    }
    raw = json.dumps(key, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def build_chart_summary(profile: BirthProfile) -> dict[str, Any]:
    """排盘 + 组装精简盘面（给 LLM 与前端共用）。

    精简原则（第 4.4 节）：全量盘面太大，只保留命理解读必需字段。
    """
    core = CalendarCore()
    result = core.compute(
        birth_date=profile.solar_birth_date,
        birth_time=profile.solar_birth_time,
        target_date=date.today(),
        gender=profile.gender,
        use_true_solar_time=profile.use_true_solar_time,
        longitude=profile.longitude,
    )

    if result.degraded:
        return {"degraded": True, "degrade_reason": result.degrade_reason}

    payload = result.payload
    bazi = payload.get("bazi") or {}
    dayun = [
        d for d in (payload.get("dayun") or []) if d.get("ganzhi")
    ]  # 过滤 lunar-python 首条空占位

    # 精确周岁：考虑是否过了本年生日（不是简单年份差）
    today = date.today()
    age_exact = today.year - profile.solar_birth_date.year - (
        (today.month, today.day) < (profile.solar_birth_date.month, profile.solar_birth_date.day)
    )

    return {
        "degraded": False,
        "bazi": bazi,
        "day_master": bazi.get("day_master", ""),
        "shishen": payload.get("shishen") or {},
        "wuxing": payload.get("bazi_wuxing") or {},
        "nayin": payload.get("nayin") or {},
        "ming_gong": payload.get("ming_gong", ""),
        "dayun": dayun,
        "liunian": future_liunian(
            today.year, FUTURE_YEARS,
            birth_year=profile.solar_birth_date.year,
            birth_month=profile.solar_birth_date.month,
            birth_day=profile.solar_birth_date.day,
        ),
        "current_age_exact": age_exact,
        "current_age_nominal": today.year - profile.solar_birth_date.year,
        "birth_time_known": profile.birth_time_known,
        "gender": profile.gender,
    }


# 批示字段（顺序即展示顺序）。解析与 prompt 都用它。
READING_KEYS = ["命格总论", "事业", "财运", "婚恋", "健康", "未来5年", "未来10年"]


def _reading_prompt(chart: dict[str, Any]) -> str:
    """构造命理批示 prompt。盘面保持精简，输出固定格式。

    注意：deepseek-v4-flash 是带思考链路（reasoning）的推理模型，
    思考过程会在独立字段返回，正文在 content 里。因此 prompt 不必
    「禁止思考」——思考链路是它的正常工作机制，压不住也不必压。
    只需约束最终正文的格式即可。
    """
    return (
        f"你是传统八字命理参考解读。以下是已排好的命盘（由确定性程序计算，"
        f"你不得自行改算）。\n\n"
        f"# 命盘\n"
        f"{_json_compact(chart)}\n\n"
        f"# 最终输出格式（严格按此格式，每行一项，冒号后是结论正文）\n"
        f"命格总论：\n"
        f"事业：\n"
        f"财运：\n"
        f"婚恋：\n"
        f"健康：\n"
        f"未来5年：\n"
        f"未来10年：\n\n"
        f"# 约束\n"
        f"- 每项 2~4 句通俗中文，不堆砌术语。\n"
        f"- 简要思考即可，重点放在结论正文，不要长篇推理。\n"
        f"- 这是传统术数参考，非科学预测，不得诊断疾病、预测死亡、"
        f"替代医疗/法律/财务建议。\n"
        f"- 若出生时辰未知，需在命格总论里说明「时柱存疑」。"
    )


def _parse_reading(text: str) -> dict[str, str] | None:
    """解析批示文本 → {字段: 内容}。

    兼容两种输出：
      1. JSON（模型偶尔会输出）；
      2. 「字段：内容」的冒号式文本（deepseek-v4-flash 实测常用此格式）。
    """
    text = (text or "").strip()
    if not text:
        return None

    # 1. 尝试 JSON（含代码块包裹）
    import json

    candidate = text
    if candidate.startswith("```"):
        inner = candidate.strip("`").strip()
        if inner.lower().startswith("json"):
            inner = inner[4:]
        candidate = inner.strip()
    try:
        data = json.loads(candidate)
        if isinstance(data, dict):
            out = {k: str(data.get(k, "")).strip() for k in READING_KEYS}
            return out if any(out.values()) else None
    except (json.JSONDecodeError, ValueError):
        pass

    # 2. 冒号式文本解析：按「字段：」切分
    out: dict[str, str] = {}
    # 找到每个字段在文本中的起始位置
    positions: list[tuple[int, str]] = []
    for key in READING_KEYS:
        # 支持全角/半角冒号
        for sep in ("：", ":"):
            idx = text.find(f"{key}{sep}")
            if idx != -1:
                positions.append((idx, key))
                break
    if not positions:
        return None
    positions.sort(key=lambda x: x[0])

    for i, (pos, key) in enumerate(positions):
        end = positions[i + 1][0] if i + 1 < len(positions) else len(text)
        # 冒号之后到下一个字段之前
        seg = text[pos:end]
        # 去掉字段名 + 冒号
        value = seg.split("：", 1)[-1].split(":", 1)[-1]
        value = value.strip()
        # 去掉可能残存的 markdown 前缀（如 "**事业**"）
        value = value.strip("*").strip()
        if value:
            out[key] = value

    return out if any(out.values()) else None


def _json_compact(obj: Any) -> str:
    import json

    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def generate_reading(session: Session, user_id: int, *, refresh: bool = False) -> dict[str, Any]:
    """生成命理批示。LLM 失败时返回确定性骨架（reading 为空 dict）。

    默认先查缓存（fortune_readings 表，按 user_id + profile_hash 命中），
    命中直接返回，避免每次进命盘页都实时调 LLM（推理模型实测 2-3 分钟）。
    传 refresh=True 强制重新生成并覆盖缓存。
    """
    profile = session.exec(
        select(BirthProfile).where(BirthProfile.user_id == user_id)
    ).first()
    if profile is None:
        return {"ok": False, "error": "未找到出生档案", "chart": None, "reading": None, "cached": False}

    profile_hash = _profile_hash(profile)

    # 1. 命中缓存直接返回
    if not refresh:
        cached = session.exec(
            select(FortuneReading)
            .where(
                FortuneReading.user_id == user_id,
                FortuneReading.profile_hash == profile_hash,
            )
            .order_by(FortuneReading.id.desc())
        ).first()
        if cached is not None and cached.chart:
            return {
                "ok": bool(cached.reading),
                "error": cached.error,
                "chart": cached.chart,
                "reading": cached.reading or None,
                "model": cached.model,
                "duration_ms": cached.duration_ms,
                "reasoning": cached.reasoning or "",
                "cached": True,
            }

    chart = build_chart_summary(profile)
    if chart.get("degraded"):
        return {
            "ok": False,
            "error": chart.get("degrade_reason"),
            "chart": chart,
            "reading": None,
            "cached": False,
        }

    from app.providers.base import LLMRequest, get_provider

    reading: dict[str, Any] | None = None
    error: str | None = None
    reasoning: str = ""
    provider = get_provider("reasoning")
    resp = provider.complete(
        LLMRequest(
            messages=[{"role": "user", "content": _reading_prompt(chart)}],
            temperature=0.5,
            # 推理模型思考链路也计入 completion tokens，与正文共享额度。
            # 思考过长会挤掉正文导致截断——已用「简要思考」约束 + 3000 兜底。
            max_tokens=3000,
        )
    )
    if resp.ok:
        reasoning = resp.reasoning
        parsed = _parse_reading(resp.content)
        if parsed:
            reading = parsed
        else:
            error = "LLM 输出无法解析为批示文本（已按确定性骨架降级）"
    else:
        error = resp.error

    # 2. 落库缓存（覆盖同 profile_hash 的旧记录，保持单条）
    if chart:
        old = session.exec(
            select(FortuneReading).where(
                FortuneReading.user_id == user_id,
                FortuneReading.profile_hash == profile_hash,
            )
        ).all()
        for o in old:
            session.delete(o)
        session.add(
            FortuneReading(
                user_id=user_id,
                profile_hash=profile_hash,
                chart=chart,
                reading=reading or {},
                reasoning=reasoning,
                model=resp.model,
                duration_ms=resp.duration_ms,
                error=error,
            )
        )
        session.commit()

    return {
        "ok": reading is not None,
        "error": error,
        "chart": chart,
        "reading": reading,
        "model": resp.model,
        "duration_ms": resp.duration_ms,
        "reasoning": reasoning,
        "cached": False,
    }
