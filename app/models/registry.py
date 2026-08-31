"""Rule Registry 与 Agent 可重放记录。

对应工程方案：
- 第 25 节 Rule Registry
- 第 36 节 数据库设计
- 第 40 节 agent_runs（每一次 LLM 调用必须可重放）
- 第 79 节 模型版本管理
"""

from __future__ import annotations

from datetime import datetime

from app.utils import utcnow
from typing import Any, Optional

from sqlalchemy import JSON, Column, Text
from sqlmodel import Field, SQLModel


class Rule(SQLModel, table=True):
    """第 25 节：每个传统规则必须有唯一 ID。

    以后可以统计：
        BAZI-R-00427
        调用次数：214
        平均增益：+0.018
        职业预测：有效 / 关系预测：无效 / 日级：无效 / 月级：有效
    """

    __tablename__ = "rules"

    id: Optional[int] = Field(default=None, primary_key=True)
    rule_id: str = Field(unique=True, index=True)

    school: str = Field(index=True, description="ziwei / bazi / qimen / liuyao / meihua / palm / face")
    description: str = Field(default="", sa_column=Column(Text))

    domains: list[str] = Field(default_factory=list, sa_type=JSON)
    supported_windows: list[str] = Field(
        default_factory=list, sa_type=JSON, description="day / week / month / year"
    )

    version: str = "1.0"
    status: str = Field(default="active", index=True, description="active / shadow / deprecated / rejected")

    # 规则定义（YAML 反序列化后的结构）
    definition: dict[str, Any] = Field(default_factory=dict, sa_type=JSON)

    created_at: datetime = Field(default_factory=utcnow)


class RuleVersion(SQLModel, table=True):
    """第 79 节：规则变更必须有版本，便于回归定位。"""

    __tablename__ = "rule_versions"

    id: Optional[int] = Field(default=None, primary_key=True)
    rule_id: str = Field(index=True)
    version: str

    definition: dict[str, Any] = Field(default_factory=dict, sa_type=JSON)
    change_note: str = ""

    created_at: datetime = Field(default_factory=utcnow)


class RuleMetric(SQLModel, table=True):
    """第 25 节：按规则 / 领域 / 时间尺度统计增益。"""

    __tablename__ = "rule_metrics"

    id: Optional[int] = Field(default=None, primary_key=True)
    rule_id: str = Field(index=True)

    domain: Optional[str] = Field(default=None, index=True)
    time_scale: Optional[str] = Field(default=None, index=True)

    call_count: int = 0
    mean_gain: float = 0.0
    brier_with: Optional[float] = None
    brier_without: Optional[float] = None

    computed_at: datetime = Field(default_factory=utcnow)


class AgentRun(SQLModel, table=True):
    """第 40 节：每一次 LLM 调用必须可重放。

    id / agent / provider / model / temperature / prompt_version /
    input_json / output_json / started_at / finished_at / tokens / error
    """

    __tablename__ = "agent_runs"

    id: Optional[int] = Field(default=None, primary_key=True)
    run_id: str = Field(unique=True, index=True)

    agent: str = Field(index=True, description="ZiweiAgent / BaziAgent / FusionAgent / ...")
    provider: str = ""
    model: str = ""
    temperature: Optional[float] = None
    tier: str = Field(default="reasoning", description="reasoning / cheap / vision（第 42 节）")

    prompt_version: str = "unknown"
    model_version: str = "unknown"

    input_json: dict[str, Any] = Field(default_factory=dict, sa_type=JSON)
    output_json: dict[str, Any] = Field(default_factory=dict, sa_type=JSON)

    started_at: datetime = Field(default_factory=utcnow)
    finished_at: Optional[datetime] = None
    duration_ms: Optional[int] = None

    tokens_in: Optional[int] = None
    tokens_out: Optional[int] = None
    error: Optional[str] = None

    # 第 12 节 Blind Multi-Agent：记录该 run 是否接触了其他 Agent 的结论
    # （第 20.11 节 AgentCollusionAttack 会检查此项）
    saw_other_agents: bool = False

    # 血缘关联
    prediction_candidate_id: Optional[str] = Field(default=None, index=True)
    prediction_id: Optional[str] = Field(default=None, index=True)


class AgentOutput(SQLModel, table=True):
    """Agent 产出的结构化内容（第 12 节：禁止相互锚定）。"""

    __tablename__ = "agent_outputs"

    id: Optional[int] = Field(default=None, primary_key=True)
    run_id: str = Field(index=True)
    agent: str = Field(index=True)

    prediction_candidate_id: Optional[str] = Field(default=None, index=True)
    prediction_id: Optional[str] = Field(default=None, index=True)

    # 结构化 Signal（第 14 节：禁止自然语言报告直接进入 Fusion）
    signal: dict[str, Any] = Field(default_factory=dict, sa_type=JSON)

    # 原始文本（仅供审计与 collusion 检测，不进入 Fusion）
    raw_text: Optional[str] = Field(default=None, sa_column=Column(Text))

    created_at: datetime = Field(default_factory=utcnow)


class PromptVersion(SQLModel, table=True):
    """第 43 节 Prompt Constitution + 第 79 节版本管理。"""

    __tablename__ = "prompt_versions"

    id: Optional[int] = Field(default=None, primary_key=True)
    prompt_key: str = Field(index=True, description="ziwei_agent / fusion / skeptic / ...")
    version: str = Field(index=True)

    content: str = Field(sa_column=Column(Text))
    checksum: str = ""

    is_active: bool = False
    change_note: str = ""
    created_at: datetime = Field(default_factory=utcnow)


class ModelVersion(SQLModel, table=True):
    """第 79 节：任何修改都需要 Model / Fusion / Prompt / Rule / Engine 五个版本号。

    若更新后性能下降 → 自动 Regression Alert。
    """

    __tablename__ = "model_versions"

    id: Optional[int] = Field(default=None, primary_key=True)
    component: str = Field(index=True, description="model / fusion / engine")
    version: str = Field(index=True)

    config: dict[str, Any] = Field(default_factory=dict, sa_type=JSON)

    is_active: bool = False
    activated_at: Optional[datetime] = None

    # 回归监控
    baseline_brier: Optional[float] = None
    current_brier: Optional[float] = None
    regression_alert: bool = False

    created_at: datetime = Field(default_factory=utcnow)
