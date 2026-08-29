"""Outcome Schema 与结果判定。

对应工程方案：
- 第 17 节 Outcome Verification
- 第 18 节 部分命中
- 第 20.13 节 ConfirmationBiasAttack（三方 Judge）
- 第 60 节 用户回复解析
- 第 61 节 现实事件 Journal
- 禁止 3：让 LLM 自己判断自己有没有预测准
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator

from .signal import Domain


class JudgeRole(str, Enum):
    """第 20.13 节：同时运行三方 Judge，防止把模糊现实描述判成「命中」。"""

    PROSECUTION = "prosecution"  # 倾向于判定「未命中」
    DEFENSE = "defense"          # 倾向于判定「命中」
    NEUTRAL = "neutral"


class OutcomeRequest(BaseModel):
    """用户验证请求。第 59 节：到期主动进入 VERIFY_REQUIRED。"""

    request_id: str = Field(default_factory=lambda: f"R-{uuid.uuid4().hex[:12]}")
    prediction_id: str
    asked_at: datetime = Field(default_factory=datetime.utcnow)
    user_reply: str | None = Field(
        default=None, description="用户自然语言回复，如「下午突然让我去处理一个事情」"
    )
    quick_answer: str | None = Field(
        default=None, description="A=发生 B=未发生 C=部分发生 D=无法判断"
    )
    answered_at: datetime | None = None


class JudgeVerdict(BaseModel):
    """单个 Judge 的判定。第 80 节要求 agent_run 可重放。"""

    judge_id: str = Field(default_factory=lambda: f"J-{uuid.uuid4().hex[:12]}")
    prediction_id: str
    role: JudgeRole
    outcome: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str
    agent_run_id: str | None = None


class Outcome(BaseModel):
    """结构化结果。第 17 节输出格式。

    第 20.13 节：三方 Judge 出现分歧则标记 needs_confirmation，
    不强行判定。
    """

    outcome_id: str = Field(default_factory=lambda: f"O-{uuid.uuid4().hex[:12]}")
    prediction_id: str
    request_id: str | None = None

    # 第 18 节：0 / 0.25 / 0.5 / 0.75 / 1.0，不强迫二值化
    outcome: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)

    evidence: str = ""
    needs_confirmation: bool = False

    verdicts: list[JudgeVerdict] = Field(default_factory=list)
    disagreement: float = Field(
        default=0.0, ge=0.0, le=1.0, description="三方 Judge 分歧度，用于 ConfirmationBiasAttack"
    )

    judged_at: datetime = Field(default_factory=datetime.utcnow)
    judge_model_version: str = "unknown"
    judge_prompt_version: str = "unknown"

    @field_validator("outcome")
    @classmethod
    def _snap_to_scale(cls, v: float) -> float:
        """第 18 节：结果必须落在预定义刻度上。"""
        allowed = (0.0, 0.25, 0.5, 0.75, 1.0)
        return min(allowed, key=lambda x: abs(x - v))

    @classmethod
    def from_verdicts(
        cls, prediction_id: str, verdicts: list[JudgeVerdict], **kwargs: Any
    ) -> "Outcome":
        """聚合三方 Judge。分歧超过阈值则请求用户确认（不强行命中）。"""
        if not verdicts:
            raise ValueError("至少需要一方 Judge 判定（禁止 3：不能让LLM自判）")

        values = [v.outcome for v in verdicts]
        disagreement = max(values) - min(values)
        mean_outcome = sum(values) / len(values)
        mean_confidence = sum(v.confidence for v in verdicts) / len(verdicts)

        # 分歧大 → 不强行判定，转人工确认
        needs_confirmation = disagreement > 0.5

        reasoning = " | ".join(f"{v.role.value}: {v.reasoning}" for v in verdicts)

        return cls(
            prediction_id=prediction_id,
            outcome=mean_outcome,
            confidence=mean_confidence if not needs_confirmation else min(mean_confidence, 0.5),
            evidence=reasoning,
            needs_confirmation=needs_confirmation,
            verdicts=verdicts,
            disagreement=disagreement,
            **kwargs,
        )


class RealityEvent(BaseModel):
    """第 61 节：现实事件 Ledger。

    验证不仅为 Prediction 服务，也沉淀为 Reality Model 的训练数据。
    数据库是权威源，Obsidian 只是人类可读展示层（第 62 节）。
    """

    event_id: str = Field(default_factory=lambda: f"E-{uuid.uuid4().hex[:12]}")
    user_id: str
    date: datetime
    domain: Domain
    event_type: str = Field(description="Event Ontology，如 career.unexpected_task")
    duration_minutes: int | None = None
    magnitude: float | None = Field(default=None, ge=0.0)
    source: str = "user_report"
    confidence: float = Field(default=0.95, ge=0.0, le=1.0)
    note: str = ""
    raw: dict[str, Any] | None = None
