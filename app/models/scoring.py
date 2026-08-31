"""结果验证与概率评分表。

对应工程方案：
- 第 36 节 数据库设计
- 第 17 节 Outcome Verification
- 第 18 节 部分命中
- 第 19 节 评分系统（Brier / LogLoss / Calibration / Sharpness / Skill Score）
- 第 19.3 节 calibration_bins
"""

from __future__ import annotations

from datetime import datetime

from app.utils import utcnow
from typing import Any, Optional

from sqlalchemy import JSON, Column, Text
from sqlmodel import Field, SQLModel


class OutcomeRequestRecord(SQLModel, table=True):
    """第 59 节：主动验证提醒。

    到期后主动进入 VERIFY_REQUIRED；用户暂不回复则 WAITING_USER，不能自动判成功。
    """

    __tablename__ = "outcome_requests"

    id: Optional[int] = Field(default=None, primary_key=True)
    request_id: str = Field(unique=True, index=True)
    prediction_id: str = Field(index=True)

    asked_at: datetime = Field(default_factory=utcnow)
    answered_at: Optional[datetime] = None

    # 第 60 节：支持自然语言回复与快捷选项
    user_reply: Optional[str] = Field(default=None, sa_column=Column(Text))
    quick_answer: Optional[str] = Field(default=None, description="A=发生 B=未发生 C=部分 D=无法判断")

    # 若可能对应多个预测，必须要求明确对应关系，不能强行命中（第 60 节）
    ambiguous: bool = False
    ambiguity_note: str = ""


class OutcomeRecord(SQLModel, table=True):
    """结构化结果。禁止 LLM 自己判断自己有没有预测准（禁止 3）。"""

    __tablename__ = "outcomes"

    id: Optional[int] = Field(default=None, primary_key=True)
    outcome_id: str = Field(unique=True, index=True)
    prediction_id: str = Field(index=True)
    request_id: Optional[str] = Field(default=None, index=True)

    # 第 18 节：0 / 0.25 / 0.5 / 0.75 / 1.0
    outcome: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)

    evidence: str = Field(default="", sa_column=Column(Text))

    # 第 20.13 节 ConfirmationBiasAttack：三方 Judge 分歧则转人工
    needs_confirmation: bool = False
    disagreement: float = 0.0

    judged_at: datetime = Field(default_factory=utcnow)
    judge_model_version: str = "unknown"
    judge_prompt_version: str = "unknown"

    # 用户最终确认（当 needs_confirmation 为真）
    user_confirmed_outcome: Optional[float] = None
    confirmed_at: Optional[datetime] = None


class OutcomeEvidence(SQLModel, table=True):
    """三方 Judge 的原始判定，用于审计与 ConfirmationBias 检测（第 20.13 节）。"""

    __tablename__ = "outcome_evidence"

    id: Optional[int] = Field(default=None, primary_key=True)
    outcome_id: str = Field(index=True)
    prediction_id: str = Field(index=True)

    role: str = Field(description="prosecution / defense / neutral")
    outcome: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str = Field(default="", sa_column=Column(Text))

    agent_run_id: Optional[str] = None
    created_at: datetime = Field(default_factory=utcnow)


class PredictionScore(SQLModel, table=True):
    """第 19 节：每条预测的评分。

    禁止 4：不能用命中率一个指标，必须概率评分。
    """

    __tablename__ = "prediction_scores"

    id: Optional[int] = Field(default=None, primary_key=True)
    prediction_id: str = Field(unique=True, index=True)
    user_id: int = Field(foreign_key="users.id", index=True)

    probability: float
    outcome: float

    # 第 19.1 节 Brier Score = (p - y)²
    brier: float

    # 第 19.2 节 Log Loss：严厉惩罚极端错误概率
    log_loss: float

    # 与 Null Model 对比（第 19.5 节 Skill Score = 1 - ModelLoss / NullLoss）
    null_probability: Optional[float] = None
    null_brier: Optional[float] = None
    skill_contribution: Optional[float] = None

    # 归因维度（第 23 / 25 / 26 节）
    domain: Optional[str] = Field(default=None, index=True)
    time_scale: Optional[str] = Field(default=None, index=True)
    source_types: list[str] = Field(default_factory=list, sa_type=JSON)
    rule_ids: list[str] = Field(default_factory=list, sa_type=JSON)

    scored_at: datetime = Field(default_factory=utcnow)


class CalibrationBin(SQLModel, table=True):
    """第 19.3 节 Calibration 分桶。

    所有标 70% 的预测，实际发生率应该接近 70%。
    如果 90% 实际只发生 76%，说明模型明显过度自信。
    """

    __tablename__ = "calibration_bins"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: Optional[int] = Field(default=None, foreign_key="users.id", index=True)

    bin_lower: float
    bin_upper: float

    sample_count: int = 0
    mean_predicted: float = 0.0
    mean_actual: float = 0.0

    # 校准误差（越小越好）
    calibration_gap: float = 0.0

    # 分组维度（第 52 节 Accuracy Lab 按术式/领域/尺度筛选）
    group_key: str = Field(default="overall", index=True, description="overall / ziwei / career / day / ...")

    computed_at: datetime = Field(default_factory=utcnow)
