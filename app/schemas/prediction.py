"""Prediction Schema 与预注册冻结。

对应工程方案：
- 第 15 节 Prediction Schema
- 第 16 节 Prediction Pre-registration（sha256 冻结）
- 第 18 节 部分命中
- 第 35 节 Hidden Prediction Mode
- C-002 / C-003：预测先于结果；不允许事后改口
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator

from .signal import Domain, Signal, TimeScale


class PredictionStatus(str, Enum):
    """预测生命周期。第 21 节 Gate 结果 + 第 59 节验证状态。"""

    CANDIDATE = "CANDIDATE"      # 候选，未过 Gate
    REJECTED = "REJECTED"        # 被对抗审查拦截（C-004 要求保留）
    REWRITE = "REWRITE"          # Gate 要求重写
    EXPERIMENTAL = "EXPERIMENTAL"  # 通过但标记为实验性，不计入主评分
    RESEARCH = "RESEARCH"        # 冷启动研究样本：用于积累校准数据，不代表预测力
    FROZEN = "FROZEN"            # 已冻结，等待验证
    VERIFY_REQUIRED = "VERIFY_REQUIRED"  # 到期，主动要求用户验证
    WAITING_USER = "WAITING_USER"        # 用户暂未回复
    VERIFIED = "VERIFIED"        # 已验证
    EXPIRED_UNVERIFIED = "EXPIRED_UNVERIFIED"  # 超期未验证
    LEAKED = "LEAKED"            # 第 20.8 节 OutcomeLeak，不进入评分


class VisibilityMode(str, Enum):
    """第 35 节 Hidden Prediction Mode：防止自我实现预言。"""

    VISIBLE = "VISIBLE"
    HIDDEN = "HIDDEN"


class OutcomeScale(float, Enum):
    """第 18 节：不要强迫所有事情二值化。

    每一种预测的 grading rule 必须在预测冻结前确定，不能事后调整。
    """

    NOT_OCCURRED = 0.0
    VERY_WEAK = 0.25
    PARTIAL = 0.5
    MOSTLY = 0.75
    FULL = 1.0


# 第 4.3 节 Information Value
# IV = Novelty × Confidence × Falsifiability × PersonalRelevance × ModelDisagreementValue
class InformationValue(BaseModel):
    novelty: float = Field(default=0.5, ge=0.0, le=1.0)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    falsifiability: float = Field(default=0.5, ge=0.0, le=1.0)
    personal_relevance: float = Field(default=0.5, ge=0.0, le=1.0)
    model_disagreement_value: float = Field(default=0.5, ge=0.0, le=1.0)

    @property
    def score(self) -> float:
        return (
            self.novelty
            * self.confidence
            * self.falsifiability
            * self.personal_relevance
            * self.model_disagreement_value
        )


class PredictionCandidate(BaseModel):
    """候选预测。候选 ≠ 正式预测（第 3.2 节）。

    第 20.6 节 MultipleTestingAttack：候选命中不得算作正式命中，
    只有冻结的 Prediction Ledger 才计分。
    """

    candidate_id: str = Field(default_factory=lambda: f"C-{uuid.uuid4().hex[:12]}")
    domain: Domain
    event_type: str = Field(description="Event Ontology，如 career.unexpected_task")
    description: str
    probability: float = Field(ge=0.0, le=1.0)
    time_scale: TimeScale = TimeScale.DAY
    window_start: datetime
    window_end: datetime

    success_criteria: list[str] = Field(default_factory=list)
    failure_criteria: list[str] = Field(default_factory=list)

    # grading rule 必须在冻结前确定（第 18 节）
    grading_rule: str = "二值：发生=1.0，未发生=0.0"

    signals: list[Signal] = Field(default_factory=list)
    information_value: InformationValue = Field(default_factory=InformationValue)

    # 第 4 节 Prediction Budget 竞争结果
    budget_granted: bool = Field(
        default=False, description="是否获得发布额度（未获得者不得进入 Prediction Ledger）"
    )
    budget_rank: int | None = Field(default=None, description="IV 排名，1 为最高")

    @field_validator("success_criteria", "failure_criteria")
    @classmethod
    def _not_empty(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("成功/失败标准不可为空（C-001 可证伪原则）")
        return v


class Prediction(BaseModel):
    """正式预测。第 15 节。

    冻结后（第 16 节）：
        UPDATE 原文 = 禁止
    如需修订只能 v1 → v2，两者都保存。
    """

    prediction_id: str = Field(default_factory=lambda: f"P-{uuid.uuid4().hex[:12]}")
    user_id: str

    domain: Domain
    event_type: str
    description: str
    probability: float = Field(ge=0.0, le=1.0)

    window_start: datetime
    window_end: datetime
    time_scale: TimeScale = TimeScale.DAY

    success_criteria: list[str]
    failure_criteria: list[str]
    grading_rule: str

    # Null Model 基线概率（第 11 节 / 第 19.5 节 Skill Score 需要）
    null_probability: float | None = Field(default=None, ge=0.0, le=1.0)

    status: PredictionStatus = PredictionStatus.FROZEN
    visibility_mode: VisibilityMode = VisibilityMode.VISIBLE

    created_at: datetime = Field(default_factory=datetime.utcnow)
    frozen_at: datetime | None = None
    verification_due_at: datetime | None = Field(
        default=None, description="第 59 节：到期主动进入 VERIFY_REQUIRED"
    )

    # 版本标识（第 79 节）
    model_version: str = "unknown"
    fusion_version: str = "unknown"
    prompt_version: str = "unknown"
    rule_version: str = "unknown"
    engine_version: str = "unknown"

    # 血缘（第 80 节 Prediction Lineage）
    candidate_id: str | None = None
    signals: list[Signal] = Field(default_factory=list)

    # 修订链（C-003）
    version: int = 1
    supersedes: str | None = None

    prediction_hash: str | None = None
    input_snapshot: dict[str, Any] | None = None

    def freeze_payload(self) -> dict[str, Any]:
        """第 16 节：冻结时参与哈希的完整字段集。"""
        return {
            "prediction_id": self.prediction_id,
            "user_id": self.user_id,
            "domain": self.domain.value,
            "event_type": self.event_type,
            "description": self.description,
            "probability": self.probability,
            "window_start": self.window_start.isoformat(),
            "window_end": self.window_end.isoformat(),
            "success_criteria": self.success_criteria,
            "failure_criteria": self.failure_criteria,
            "grading_rule": self.grading_rule,
            "null_probability": self.null_probability,
            "version": self.version,
            "signals": [s.model_dump(mode="json") for s in self.signals],
            "model_version": self.model_version,
            "fusion_version": self.fusion_version,
            "prompt_version": self.prompt_version,
            "rule_version": self.rule_version,
            "engine_version": self.engine_version,
        }

    @staticmethod
    def hash_payload(payload: dict[str, Any]) -> str:
        """对任意冻结载荷计算 sha256。

        独立于实例，便于直接校验库里取回的 freeze_payload
        （第 20.7 节 RetrofittingAttack）。
        """
        raw = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def compute_hash(self) -> str:
        """sha256 冻结哈希（第 15 / 16 节）。

        任何事后改动都会导致哈希不匹配 → 第 20.7 节 RetrofittingAttack 检出。
        """
        return self.hash_payload(self.freeze_payload())

    def freeze(self) -> "Prediction":
        """冻结预测：写入 frozen_at、计算哈希、置为 FROZEN。"""
        self.frozen_at = datetime.utcnow()
        self.prediction_hash = self.compute_hash()
        self.status = PredictionStatus.FROZEN
        if self.verification_due_at is None:
            self.verification_due_at = self.window_end
        return self

    def verify_integrity(self) -> bool:
        """校验预测原文是否被篡改（第 20.7 节）。"""
        if not self.prediction_hash:
            return False
        return self.compute_hash() == self.prediction_hash

    def create_revision(self, **changes: Any) -> "Prediction":
        """C-003：修订只能新增版本，原版本永久存在。"""
        data = self.model_dump()
        data.pop("prediction_id", None)
        data.update(changes)
        data["version"] = self.version + 1
        data["supersedes"] = self.prediction_id
        data["status"] = PredictionStatus.CANDIDATE
        data["frozen_at"] = None
        data["prediction_hash"] = None
        return Prediction(**data)
