"""基础档案表：users / birth_profiles / calendar_snapshots。

对应工程方案第 36 节。
隐私：birth_profiles 属高敏感个人数据（第 64 节，本地优先）。
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional

from sqlalchemy import JSON
from sqlmodel import Field, SQLModel

from .base import TimestampMixin


class User(SQLModel, table=True):
    __tablename__ = "users"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_key: str = Field(unique=True, index=True, description="外部稳定标识")
    display_name: str = ""
    timezone: str = "Asia/Shanghai"
    is_active: bool = True


class BirthProfile(SQLModel, table=True):
    """出生档案。第 6 节八字/历法要求统一 Calendar Core。

    所有术式必须共享同一个 Calendar Core，禁止各模块自己算日期。
    """

    __tablename__ = "birth_profiles"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)

    # 公历出生时刻
    solar_birth_date: date
    solar_birth_time: str = Field(default="00:00", description="HH:MM，未知则用 00:00")
    birth_time_known: bool = Field(
        default=False, description="出生时辰是否确定。不确定时相关术式必须降低 confidence。"
    )

    gender: str = Field(default="unknown", description="male / female / unknown")
    birth_place: str = ""
    longitude: Optional[float] = None
    latitude: Optional[float] = None

    # 真太阳时校正（第 6 节：八字依赖真太阳时）
    use_true_solar_time: bool = True

    is_primary: bool = True


class CalendarSnapshot(SQLModel, table=True):
    """Calendar Core 计算快照。

    第 6 节要求统一：公历、农历、节气、干支、四柱、五行、十神、大运、流年、流月、流日。
    第 54 节：deterministic 计算必须可 golden-case 复现。
    """

    __tablename__ = "calendar_snapshots"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)

    # 第 54 节：golden case 比对锚点 —— 相同输入必须产生相同输出
    input_hash: str = Field(index=True, description="计算输入的 sha256")

    # 查询时刻
    target_date: date = Field(index=True)
    target_time: str = "00:00"

    # --- 四柱（年/月/日/时）---
    year_ganzhi: str = ""
    month_ganzhi: str = ""
    day_ganzhi: str = ""
    hour_ganzhi: str = ""

    # --- 农历 ---
    lunar_year: Optional[int] = None
    lunar_month: Optional[int] = None
    lunar_day: Optional[int] = None
    is_leap_month: bool = False

    # --- 节气 ---
    current_jieqi: str = ""
    jieqi_date: Optional[date] = None
    days_to_next_jieqi: Optional[int] = None

    # --- 大运 / 流年 ---
    dayun_ganzhi: str = ""
    dayun_start_age: Optional[float] = None
    liunian_ganzhi: str = ""
    liuyue_ganzhi: str = ""
    liuri_ganzhi: str = ""

    # 完整计算结果（五行、十神、纳音等）
    payload: dict[str, Any] = Field(default_factory=dict, sa_type=JSON)

    engine_version: str = "calendar-0.1.0"
    computed_at: datetime = Field(default_factory=datetime.utcnow)
