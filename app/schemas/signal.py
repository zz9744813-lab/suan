"""统一 Signal Schema。

对应工程方案：
- 第 14 节 统一 Signal Schema
- 第 55 节 数据来源分层
- 第 56 节 预测领域词典（Event Ontology）
- 第 20.12 节 CorrelatedEvidenceAttack（dependency_group）

硬性约束（第 14 节）：
    禁止自然语言报告直接进入 Fusion。
    所有术式输出必须转换为统一 Signal。

硬性约束（第 55 节）：
    禁止把 LLM 推测伪装成传统规则事实。
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator


# --------------------------------------------------------------------------
# 第 6-11 节：信号来源
# --------------------------------------------------------------------------
class SourceType(str, Enum):
    """信号来源系统。NullAgent 是「完全不知道任何术数」的基线（第 11 节）。"""

    ZIWEI = "ziwei"
    BAZI = "bazi"
    QIMEN = "qimen"
    LIUYAO = "liuyao"
    MEIHUA = "meihua"
    PALM = "palm"
    FACE = "face"
    REALITY = "reality"
    NULL = "null"


# --------------------------------------------------------------------------
# 第 3.2 节：候选领域
# --------------------------------------------------------------------------
class Domain(str, Enum):
    CAREER = "career"
    MONEY = "money"
    STUDY = "study"
    SOCIAL = "social"
    RELATIONSHIP = "relationship"
    TRAVEL = "travel"
    PROJECT = "project"
    HABIT = "habit"
    PURCHASE = "purchase"
    COMMUNICATION = "communication"
    SCHEDULE = "schedule"
    UNEXPECTED_EVENT = "unexpected_event"


# --------------------------------------------------------------------------
# 第 57 节：时间尺度
# --------------------------------------------------------------------------
class TimeScale(str, Enum):
    DAY = "day"
    WEEK = "week"
    MONTH = "month"
    YEAR = "year"


# --------------------------------------------------------------------------
# 第 55 节：数据来源分层
# --------------------------------------------------------------------------
class EvidenceSource(str, Enum):
    """每条 Evidence 必须标记来源。

    禁止把 LLM 推测伪装成传统规则事实。
    """

    TRADITIONAL_RULE = "TRADITIONAL_RULE"
    CALENDAR = "CALENDAR"
    USER_REPORTED_REALITY = "USER_REPORTED_REALITY"
    USER_PLAN = "USER_PLAN"
    HISTORICAL_PATTERN = "HISTORICAL_PATTERN"
    LLM_INFERENCE = "LLM_INFERENCE"
    EXTERNAL_DATA = "EXTERNAL_DATA"


# 第 57 节默认时间尺度约束表。
# 权重最终仍以实际实验结果覆盖（由 Reliability Matrix 学习）。
DEFAULT_SCALE_SUPPORT: dict[SourceType, dict[TimeScale, float]] = {
    SourceType.ZIWEI: {TimeScale.DAY: 0.0, TimeScale.WEEK: 0.5, TimeScale.MONTH: 0.9, TimeScale.YEAR: 0.9},
    SourceType.BAZI: {TimeScale.DAY: 0.5, TimeScale.WEEK: 0.5, TimeScale.MONTH: 0.9, TimeScale.YEAR: 0.9},
    SourceType.QIMEN: {TimeScale.DAY: 0.9, TimeScale.WEEK: 0.9, TimeScale.MONTH: 0.0, TimeScale.YEAR: 0.0},
    SourceType.LIUYAO: {TimeScale.DAY: 0.9, TimeScale.WEEK: 0.9, TimeScale.MONTH: 0.5, TimeScale.YEAR: 0.0},
    SourceType.MEIHUA: {TimeScale.DAY: 0.9, TimeScale.WEEK: 0.5, TimeScale.MONTH: 0.0, TimeScale.YEAR: 0.0},
    SourceType.PALM: {TimeScale.DAY: 0.0, TimeScale.WEEK: 0.0, TimeScale.MONTH: 0.2, TimeScale.YEAR: 0.2},
    SourceType.FACE: {TimeScale.DAY: 0.0, TimeScale.WEEK: 0.0, TimeScale.MONTH: 0.2, TimeScale.YEAR: 0.2},
    SourceType.REALITY: {TimeScale.DAY: 0.9, TimeScale.WEEK: 0.9, TimeScale.MONTH: 0.9, TimeScale.YEAR: 0.5},
    SourceType.NULL: {ts: 1.0 for ts in TimeScale},
}


class Evidence(BaseModel):
    """一条证据。第 55 节要求必须标记来源。"""

    source: EvidenceSource
    rule_id: str | None = None
    description: str
    weight: float = Field(default=1.0, ge=0.0, le=1.0)


class TimeWindow(BaseModel):
    """预测/信号的时间窗口。第 20.4 节 TimeWindowAttack 要求必须明确。"""

    start: datetime
    end: datetime

    @field_validator("end")
    @classmethod
    def _end_after_start(cls, v: datetime, info: Any) -> datetime:
        start = info.data.get("start")
        if start is not None and v <= start:
            raise ValueError("time_window.end 必须晚于 start")
        return v


class Signal(BaseModel):
    """统一 Signal。所有术式输出的中转格式（第 14 节）。

    direction: -1.0 ~ 1.0，事件发生的倾向方向（负=抑制）
    strength:  0.0 ~ 1.0，信号力度
    confidence:0.0 ~ 1.0，该信号自身的置信度（第 43 节：信息不足时必须降低）
    """

    signal_id: str = Field(default_factory=lambda: f"S-{uuid.uuid4().hex[:12]}")
    source: SourceType
    domain: Domain
    target_event: str = Field(description="Event Ontology 中的事件类型，如 career.unexpected_task")

    direction: float = Field(ge=-1.0, le=1.0)
    strength: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)

    time_window: TimeWindow
    time_scale: TimeScale = TimeScale.DAY

    evidence: list[Evidence] = Field(default_factory=list)
    counter_evidence: list[Evidence] = Field(default_factory=list)
    rule_ids: list[str] = Field(default_factory=list)

    # 第 20.12 节：紫微、八字、黄历可能共享同类历法信号，
    # 不能把「4 个术式支持」错误理解成「4 个独立证据」。
    # 同一 dependency_group 内的信号在 Fusion 时降低重复计权。
    dependency_group: str | None = Field(
        default=None,
        description="证据依赖分组，如 'lunar_calendar'。同组信号在 Fusion 中去重计权。",
    )

    # 第 79 节模型版本管理
    engine_version: str = "unknown"
    prompt_version: str | None = None

    # 引擎缺失 / 降级时（如未安装 lunar-python）标记，Fusion 需跳过而非当作 0。
    degraded: bool = False
    degrade_reason: str | None = None

    @property
    def signed_strength(self) -> float:
        """带方向的强度，用于 Fusion 加权。"""
        return self.direction * self.strength

    @property
    def effective_weight(self) -> float:
        """置信度加权后的有效力度。"""
        return self.signed_strength * self.confidence

    def scale_support(self) -> float:
        """该信号在其时间尺度上的先验支持度（第 57 节）。"""
        return DEFAULT_SCALE_SUPPORT.get(self.source, {}).get(self.time_scale, 0.0)
