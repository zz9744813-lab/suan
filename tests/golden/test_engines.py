"""Golden Cases —— 术式引擎确定性测试。

对应工程方案第 54 节：

    输入完全相同 → 排盘必须完全相同。
    LLM 解释可以变化，排盘不能变化。

每类测试同时验证：
    1. 确定性（同输入同输出）；
    2. 结构完整性（关键字段存在）；
    3. 已知输入 → 已知输出的锚点校验。
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta

import pytest

from app.core.base import AdapterQuery
from app.schemas.signal import Domain, TimeScale, TimeWindow

# ---------------------------------------------------------------
# 共享测试夹具
# ---------------------------------------------------------------
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import app.core  # noqa: F401 触发全部 Adapter 注册
import app.models  # noqa: F401
from app.models.core import BirthProfile, User


@pytest.fixture()
def ctx():
    """带出生档案的测试上下文（1990-05-15 14:30 男，北京）。"""
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        u = User(user_key="golden")
        s.add(u)
        s.commit()
        s.refresh(u)
        s.add(
            BirthProfile(
                user_id=u.id,
                solar_birth_date=date(1990, 5, 15),
                solar_birth_time="14:30",
                birth_time_known=True,
                gender="male",
            )
        )
        s.commit()
        start = datetime(2026, 9, 1)
        q = AdapterQuery(
            user_id=u.id,
            domain=Domain.CAREER,
            target_event="career.unexpected_task",
            time_scale=TimeScale.DAY,
            window=TimeWindow(start=start, end=start + timedelta(hours=1)),
            target_date=date(2026, 9, 1),
            target_time="14:30",
            session=s,
        )
        yield q


# ---------------------------------------------------------------
# 八字（第 6.1 节）
# ---------------------------------------------------------------
def test_bazi_deterministic(ctx):
    from app.core.calendar.core import CalendarCore

    core = CalendarCore()
    a = core.compute(birth_date=date(1990, 5, 15), birth_time="14:30",
                     target_date=date(2026, 9, 1), gender="male")
    b = core.compute(birth_date=date(1990, 5, 15), birth_time="14:30",
                     target_date=date(2026, 9, 1), gender="male")
    assert json.dumps(a.payload) == json.dumps(b.payload)


def test_bazi_golden_anchors(ctx):
    """第 54 节锚点：已知输入 → 已知四柱。"""
    from app.core.calendar.core import CalendarCore

    core = CalendarCore()
    r = core.compute(birth_date=date(1990, 5, 15), birth_time="14:30",
                     target_date=date(2026, 9, 1), gender="male")
    assert r.payload["bazi"]["year"] == "庚午"
    assert r.payload["bazi"]["month"] == "辛巳"
    assert r.payload["bazi"]["day"] == "庚辰"
    assert r.payload["bazi"]["time"] == "癸未"
    assert r.payload["bazi"]["day_master"] == "庚"


def test_bazi_adapter_outputs_signal(ctx):
    from app.core.base import registry

    adapter = registry.get("bazi")
    sigs = adapter.signals(ctx)
    assert sigs and not sigs[0].degraded
    assert sigs[0].rule_ids and sigs[0].rule_ids[0].startswith("BAZI-R-")


# ---------------------------------------------------------------
# 六爻（第 6.1 节）
# ---------------------------------------------------------------
def test_liuyao_deterministic(ctx):
    from app.core.liuyao.engine import cast_chart

    a = cast_chart(datetime(2026, 9, 1, 14, 30), birth_date=date(1990, 5, 15))
    b = cast_chart(datetime(2026, 9, 1, 14, 30), birth_date=date(1990, 5, 15))
    assert json.dumps(a) == json.dumps(b)


def test_liuyao_structure(ctx):
    from app.core.liuyao.engine import cast_chart

    chart = cast_chart(datetime(2026, 9, 1, 14, 30), birth_date=date(1990, 5, 15))
    assert "ben_gua" in chart
    assert "yao_details" in chart
    assert len(chart["yao_details"]) == 6
    assert "shi_yao_index" in chart
    assert "xunkong" in chart
    # 世应必须存在且不同
    assert chart["shi_yao_index"] != chart["ying_yao_index"]
    # 每爻有六亲六神
    for y in chart["yao_details"]:
        assert y["liuqin"] in ("父母", "兄弟", "子孙", "妻财", "官鬼")
        assert y["liushou"] in ("青龙", "朱雀", "勾陈", "螣蛇", "白虎", "玄武")


def test_liuyao_adapter_outputs_signal(ctx):
    from app.core.base import registry

    adapter = registry.get("liuyao")
    sigs = adapter.signals(ctx)
    assert sigs and not sigs[0].degraded
    assert sigs[0].rule_ids[0].startswith("LIUYAO-R-")


# ---------------------------------------------------------------
# 梅花（第 6.1 节）
# ---------------------------------------------------------------
def test_meihua_deterministic(ctx):
    from app.core.meihua.engine import cast_by_time

    a = cast_by_time(datetime(2026, 9, 1, 14, 30))
    b = cast_by_time(datetime(2026, 9, 1, 14, 30))
    assert json.dumps(a) == json.dumps(b)


def test_meihua_structure(ctx):
    from app.core.meihua.engine import cast_by_time

    chart = cast_by_time(datetime(2026, 9, 1, 14, 30))
    assert "ben_gua" in chart and "hu_gua" in chart and "bian_gua" in chart
    assert "ti_gua" in chart and "yong_gua" in chart
    assert chart["relation"] in ("用生体", "体克用", "比和", "体生用", "用克体")
    assert 1 <= chart["moving_yao"] <= 6


def test_meihua_adapter_outputs_signal(ctx):
    from app.core.base import registry

    adapter = registry.get("meihua")
    sigs = adapter.signals(ctx)
    assert sigs and not sigs[0].degraded
    assert sigs[0].rule_ids[0].startswith("MEIHUA-R-")


# ---------------------------------------------------------------
# 奇门（第 6.1 节）
# ---------------------------------------------------------------
def test_qimen_deterministic(ctx):
    from app.core.qimen.engine import cast_chart

    a = cast_chart(datetime(2026, 9, 1, 14, 30))
    b = cast_chart(datetime(2026, 9, 1, 14, 30))
    assert json.dumps(a) == json.dumps(b)


def test_qimen_structure(ctx):
    from app.core.qimen.engine import cast_chart

    chart = cast_chart(datetime(2026, 9, 1, 14, 30))
    assert "dun_type" in chart and "ju_number" in chart and "yuan" in chart
    palaces = chart.get("palaces", [])
    assert len(palaces) == 9
    # 每宫有门/星/天干（中宫除外）
    for p in palaces:
        if not p.get("is_center"):
            assert p["door"] and p["star"]
    assert "zhifu" in chart


def test_qimen_adapter_outputs_signal(ctx):
    from app.core.base import registry

    adapter = registry.get("qimen")
    sigs = adapter.signals(ctx)
    # 值符宫门为吉/凶之一时应有信号；否则诚实无信号
    if sigs:
        assert not sigs[0].degraded


# ---------------------------------------------------------------
# 紫微（第 6.1 节）
# ---------------------------------------------------------------
def test_ziwei_deterministic(ctx):
    """第 54 节：同输入同盘。iztro-py 的 Astrolabe 序列化用结构化快照比较。"""
    from iztro_py import astro

    def snapshot(chart):
        return [
            {"palace": p.translate_name(),
             "stars": [s.name for s in (p.major_stars or [])]}
            for p in chart.palaces
        ]

    a = astro.by_solar("1990-5-15", 8, "男")
    b = astro.by_solar("1990-5-15", 8, "男")
    assert snapshot(a) == snapshot(b)


def test_ziwei_structure(ctx):
    from iztro_py import astro

    chart = astro.by_solar("1990-5-15", 8, "男")
    assert len(chart.palaces) == 12
    names = [p.translate_name() for p in chart.palaces]
    assert "命宫" in names and "官禄宫" in names and "财帛宫" in names


def test_ziwei_adapter_outputs_signal(ctx):
    from app.core.base import registry

    adapter = registry.get("ziwei")
    sigs = adapter.signals(ctx)
    # 官禄宫为空宫时应借对宫（夫妻宫武曲贪狼），产出信号
    assert sigs and not sigs[0].degraded
    assert sigs[0].rule_ids[0].startswith("ZIWEI-R-")


# ---------------------------------------------------------------
# 掌纹 / 面相（第 8 / 9 节）
# ---------------------------------------------------------------
def test_palm_degrades_without_image(ctx):
    """第 8 节：无照片时必须诚实降级，不硬猜。"""
    from app.core.base import registry

    adapter = registry.get("palm")
    sigs = adapter.signals(ctx)
    assert sigs and sigs[0].degraded


def test_face_degrades_without_image(ctx):
    """第 9 节：无照片时必须诚实降级。"""
    from app.core.base import registry

    adapter = registry.get("face")
    sigs = adapter.signals(ctx)
    assert sigs and sigs[0].degraded
