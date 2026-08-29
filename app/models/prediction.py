"""Prediction Ledger 表。

对应工程方案：
- 第 36 节 数据库设计
- 第 37 节 prediction 表
- 第 38 节 signal 表
- 第 15 / 16 节 Prediction Schema 与预注册冻结
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import JSON, Column, Text
from sqlmodel import Field, SQLModel


class ForecastCandidate(SQLModel, table=True):
    """第 3.2 节 候选池。候选 ≠ 正式预测。

    第 20.6 节 MultipleTestingAttack：候选命中不得算作正式命中，
    只有冻结的 Prediction Ledger 才计分。
    """

    __tablename__ = "forecast_candidates"

    id: Optional[int] = Field(default=None, primary_key=True)
    candidate_id: str = Field(unique=True, index=True)
    user_id: int = Field(foreign_key="users.id", index=True)

    domain: str = Field(index=True)
    event_type: str = Field(index=True)
    description: str = Field(sa_column=Column(Text))

    probability: float = Field(ge=0.0, le=1.0)
    time_scale: str = Field(default="day", index=True)
    window_start: datetime
    window_end: datetime

    success_criteria: list[str] = Field(default_factory=list, sa_type=JSON)
    failure_criteria: list[str] = Field(default_factory=list, sa_type=JSON)
    grading_rule: str = "二值：发生=1.0，未发生=0.0"

    # 第 4.3 节 Information Value
    information_value: dict[str, Any] = Field(default_factory=dict, sa_type=JSON)
    iv_score: float = Field(default=0.0, index=True)

    # Gate 结果：PASS / REWRITE / REJECT / EXPERIMENTAL（第 21 节）
    gate_status: Optional[str] = Field(default=None, index=True)
    gate_reason: str = ""

    # 预算竞争：是否获得发布额度（第 4 节）
    budget_granted: bool = False
    budget_rank: Optional[int] = None

    created_at: datetime = Field(default_factory=datetime.utcnow)
    model_version: str = "unknown"


class SignalRecord(SQLModel, table=True):
    """第 38 节 signal 表。统一 Signal Schema 的持久化形式（第 14 节）。"""

    __tablename__ = "signals"

    id: Optional[int] = Field(default=None, primary_key=True)
    signal_id: str = Field(unique=True, index=True)
    prediction_candidate_id: Optional[str] = Field(default=None, index=True)
    prediction_id: Optional[str] = Field(default=None, index=True)

    source_type: str = Field(index=True, description="ziwei / bazi / qimen / liuyao / meihua / palm / face / reality / null")
    source_engine: str = ""

    domain: str = Field(index=True)
    target_event: str = Field(index=True)

    direction: float = Field(ge=-1.0, le=1.0)
    strength: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)

    time_scale: str = "day"
    window_start: datetime
    window_end: datetime

    evidence: list[dict[str, Any]] = Field(default_factory=list, sa_type=JSON)
    counter_evidence: list[dict[str, Any]] = Field(default_factory=list, sa_type=JSON)
    rule_ids: list[str] = Field(default_factory=list, sa_type=JSON)

    # 第 20.12 节 CorrelatedEvidenceAttack：同组证据降低重复计权
    dependency_group: Optional[str] = Field(default=None, index=True)

    engine_version: str = "unknown"
    prompt_version: Optional[str] = None
    degraded: bool = False
    degrade_reason: Optional[str] = None

    created_at: datetime = Field(default_factory=datetime.utcnow)


class PredictionRecord(SQLModel, table=True):
    """第 37 节 prediction 表。正式预测账本。

    冻结后：UPDATE 原文 = 禁止（第 16 节）。
    """

    __tablename__ = "predictions"

    id: Optional[int] = Field(default=None, primary_key=True)
    prediction_id: str = Field(unique=True, index=True)
    user_id: int = Field(foreign_key="users.id", index=True)

    domain: str = Field(index=True)
    event_type: str = Field(index=True)
    description: str = Field(sa_column=Column(Text))

    probability: float = Field(ge=0.0, le=1.0, index=True)
    null_probability: Optional[float] = None

    time_scale: str = Field(default="day", index=True)
    window_start: datetime = Field(index=True)
    window_end: datetime = Field(index=True)

    success_criteria: list[str] = Field(default_factory=list, sa_type=JSON)
    failure_criteria: list[str] = Field(default_factory=list, sa_type=JSON)
    grading_rule: str = ""

    status: str = Field(default="FROZEN", index=True)
    visibility_mode: str = Field(default="VISIBLE", description="第 35 节 Hidden Prediction Mode")

    created_at: datetime = Field(default_factory=datetime.utcnow)
    frozen_at: Optional[datetime] = None
    verification_due_at: Optional[datetime] = Field(default=None, index=True)

    # 第 16 节：内容哈希，事后篡改会被第 20.7 节 RetrofittingAttack 检出
    sha256: Optional[str] = Field(default=None, index=True)

    # 第 79 节 版本管理
    model_version: str = "unknown"
    fusion_version: str = "unknown"
    prompt_version: str = "unknown"
    rule_version: str = "unknown"
    engine_version: str = "unknown"

    # 第 80 节 Prediction Lineage
    candidate_id: Optional[str] = Field(default=None, index=True)

    # C-003 修订链
    version: int = Field(default=1)
    supersedes: Optional[str] = Field(default=None, index=True)


class PredictionVersion(SQLModel, table=True):
    """C-003：修订只能 v1 → v2，原版本永久存在。"""

    __tablename__ = "prediction_versions"

    id: Optional[int] = Field(default=None, primary_key=True)
    prediction_id: str = Field(index=True)
    version: int

    snapshot: dict[str, Any] = Field(default_factory=dict, sa_type=JSON)
    sha256: str = ""

    revision_reason: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)


class PredictionFreeze(SQLModel, table=True):
    """第 16 节 Prediction Pre-registration 完整快照。

    冻结时保存：prediction / probability / time_window / success_criteria /
    failure_criteria / all_signals / all_agent_outputs / input_snapshot /
    model / provider / prompt_version / rule_version / engine_version / timestamp / sha256
    """

    __tablename__ = "prediction_freezes"

    id: Optional[int] = Field(default=None, primary_key=True)
    prediction_id: str = Field(unique=True, index=True)

    # 完整冻结载荷（参与哈希的字段）
    freeze_payload: dict[str, Any] = Field(default_factory=dict, sa_type=JSON)

    # 所有 Agent 输出（第 12 节 Blind Multi-Agent 要求可回溯各 Agent 独立结论）
    agent_outputs: list[dict[str, Any]] = Field(default_factory=list, sa_type=JSON)

    # 输入快照：命盘 / RealityState / 候选池等
    input_snapshot: dict[str, Any] = Field(default_factory=dict, sa_type=JSON)

    sha256: str = Field(index=True)
    frozen_at: datetime = Field(default_factory=datetime.utcnow)

    # 第 20.7 节：事后校验时记录
    last_integrity_check_at: Optional[datetime] = None
    integrity_ok: Optional[bool] = None
