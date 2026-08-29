"""误差驱动学习表。

对应工程方案：
- 第 22 节 Prediction Error Driven Learning
- 第 23 节 失败归因
- 第 24 节 禁止直接在线自修改（Shadow Mode）
- 第 33 节 Ablation Test
- 第 34 节 双盲实验模式
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import JSON, Column, Text
from sqlmodel import Field, SQLModel


class LearningHypothesis(SQLModel, table=True):
    """第 23 节：预测失败不是异常，预测失败是训练数据。

    例：
        H1: 传统模型整体过度自信
        H2: 三个术式存在相关证据重复计权
        H3: Reality 明显反对，但 Fusion 权重不足
        H4: 事件类别定义过宽
        H5: 流日规则存在错误
    """

    __tablename__ = "learning_hypotheses"

    id: Optional[int] = Field(default=None, primary_key=True)
    hypothesis_id: str = Field(unique=True, index=True)
    prediction_id: Optional[str] = Field(default=None, index=True)

    statement: str = Field(sa_column=Column(Text))
    category: str = Field(
        index=True,
        description="overconfidence / correlated_evidence / fusion_weight / definition / rule_error / other",
    )

    # 证据支撑
    supporting_evidence: dict[str, Any] = Field(default_factory=dict, sa_type=JSON)

    # 归因目标（第 26 节 Personal Reliability Matrix 的维度）
    target_system: Optional[str] = Field(default=None, index=True)
    target_domain: Optional[str] = Field(default=None, index=True)
    target_time_scale: Optional[str] = Field(default=None, index=True)
    target_rule_ids: list[str] = Field(default_factory=list, sa_type=JSON)

    status: str = Field(default="proposed", index=True, description="proposed / shadow / promoted / rejected")
    proposed_at: datetime = Field(default_factory=datetime.utcnow)


class ShadowExperiment(SQLModel, table=True):
    """第 24 节：LearningAgent 不能因为一次失败就修改生产规则。

    Production Model
      ├── Current Rule
      └── Candidate Rule → Shadow Mode → 50/100 样本 → Statistical Review → Promote
    """

    __tablename__ = "shadow_experiments"

    id: Optional[int] = Field(default=None, primary_key=True)
    experiment_id: str = Field(unique=True, index=True)
    hypothesis_id: Optional[str] = Field(default=None, index=True)

    name: str
    description: str = Field(default="", sa_column=Column(Text))

    # 候选规则配置
    candidate_config: dict[str, Any] = Field(default_factory=dict, sa_type=JSON)

    started_at: datetime = Field(default_factory=datetime.utcnow)
    target_sample_size: int = Field(default=50, description="第 24 节：50 / 100 个样本后再评审")
    current_sample_size: int = 0

    production_brier: Optional[float] = None
    candidate_brier: Optional[float] = None

    status: str = Field(default="running", index=True, description="running / reviewing / promoted / rejected")
    review_note: str = ""

    # 第 33 节 Ablation Test：记录被移除的模块
    ablation_target: Optional[str] = Field(
        default=None, index=True, description="ziwei / bazi / qimen / liuyao / reality / null"
    )


class ModelPromotion(SQLModel, table=True):
    """第 24 / 79 节：候选规则通过统计评审后正式升级。"""

    __tablename__ = "model_promotions"

    id: Optional[int] = Field(default=None, primary_key=True)
    experiment_id: str = Field(index=True)

    component: str = Field(description="rule / fusion / prompt / model / engine")
    component_id: str = Field(description="rule_id / fusion_version / prompt_key ...")

    from_version: str
    to_version: str

    # 统计评审依据
    sample_size: int = 0
    brier_before: Optional[float] = None
    brier_after: Optional[float] = None
    improvement: Optional[float] = None
    p_value: Optional[float] = None

    promoted_at: datetime = Field(default_factory=datetime.utcnow)
    promoted_by: str = Field(default="system", description="system / user")

    # 第 79 节：升级后性能下降需自动 Regression Alert
    regression_alert: bool = False
    rolled_back_at: Optional[datetime] = None


class AblationResult(SQLModel, table=True):
    """第 33 节 Ablation Test 结果。

    系统应允许得到「不好听」的结果，例如：
        Reality：强贡献
        Qimen：强贡献
        Liuyao：弱贡献
        Ziwei：很弱贡献
        Bazi：当前无贡献
    """

    __tablename__ = "ablation_results"

    id: Optional[int] = Field(default=None, primary_key=True)
    run_id: str = Field(index=True)

    variant: str = Field(index=True, description="full / -ziwei / -bazi / -qimen / -liuyao / -reality / null_only")

    sample_size: int = 0
    brier: Optional[float] = None
    log_loss: Optional[float] = None
    skill_score: Optional[float] = None

    computed_at: datetime = Field(default_factory=datetime.utcnow)


class ExperimentRun(SQLModel, table=True):
    """第 34 节 双盲实验模式。

    Experiment A: Reality + Null
    Experiment B: Metaphysical Only
    Experiment C: Reality + Metaphysical
    全部在不知道彼此结果的情况下预测，长期比较。
    """

    __tablename__ = "experiment_runs"

    id: Optional[int] = Field(default=None, primary_key=True)
    run_id: str = Field(unique=True, index=True)

    mode: str = Field(index=True, description="blind_ab / hidden / normal")
    arm: str = Field(index=True, description="A_reality_null / B_metaphysical_only / C_fusion / null_only")

    started_at: datetime = Field(default_factory=datetime.utcnow)
    ended_at: Optional[datetime] = None

    sample_size: int = 0
    brier: Optional[float] = None

    note: str = ""
