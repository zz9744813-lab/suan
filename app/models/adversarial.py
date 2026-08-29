"""对抗性审查表。

对应工程方案：
- 第 20 节 对抗性审查系统（14 种 Attack）
- 第 21 节 对抗性 Gate
- 第 39 节 adversarial_tests 表

第 20 节开宗明义：这是核心基础设施，不是附属 Agent。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import JSON, Column, Text
from sqlmodel import Field, SQLModel


class AttackType:
    """第 20.1 - 20.14 节定义的 14 种攻击。"""

    VAGUENESS = "VaguenessAttack"
    BARNUM = "BarnumAttack"
    DEFINITION = "DefinitionAttack"
    TIME_WINDOW = "TimeWindowAttack"
    CHERRY_PICK = "CherryPickAttack"
    MULTIPLE_TESTING = "MultipleTestingAttack"
    RETROFITTING = "RetrofittingAttack"
    OUTCOME_LEAK = "OutcomeLeakAttack"
    SELF_FULFILLING = "SelfFulfillingAttack"
    BASELINE = "BaselineAttack"
    AGENT_COLLUSION = "AgentCollusionAttack"
    CORRELATED_EVIDENCE = "CorrelatedEvidenceAttack"
    CONFIRMATION_BIAS = "ConfirmationBiasAttack"
    NARRATIVE_EXCUSE = "NarrativeExcuseAttack"

    ALL: list[str] = [
        VAGUENESS,
        BARNUM,
        DEFINITION,
        TIME_WINDOW,
        OUTCOME_LEAK,
        CHERRY_PICK,
        MULTIPLE_TESTING,
        RETROFITTING,
        SELF_FULFILLING,
        BASELINE,
        AGENT_COLLUSION,
        CORRELATED_EVIDENCE,
        CONFIRMATION_BIAS,
        NARRATIVE_EXCUSE,
    ]


class AttackResult:
    """单项攻击结论。"""

    PASS = "PASS"
    FAIL = "FAIL"
    WARN = "WARN"
    SKIP = "SKIP"


class GateDecision:
    """第 21 节 Gate 结果。只有 PASS 可以进入正式 Prediction Ledger。"""

    PASS = "PASS"
    REWRITE = "REWRITE"
    REJECT = "REJECT"
    EXPERIMENTAL = "EXPERIMENTAL"


class AdversarialTest(SQLModel, table=True):
    """第 39 节 adversarial_tests 表。"""

    __tablename__ = "adversarial_tests"

    id: Optional[int] = Field(default=None, primary_key=True)
    candidate_id: Optional[str] = Field(default=None, index=True)
    prediction_id: Optional[str] = Field(default=None, index=True)

    attack_type: str = Field(index=True)
    result: str = Field(index=True, description="PASS / FAIL / WARN / SKIP")

    severity: float = Field(default=0.0, ge=0.0, le=1.0)
    reason: str = Field(default="", sa_column=Column(Text))

    agent_run_id: Optional[str] = None
    details: dict[str, Any] = Field(default_factory=dict, sa_type=JSON)

    created_at: datetime = Field(default_factory=datetime.utcnow)


class AdversarialFinding(SQLModel, table=True):
    """聚合结论：一次 Gate 运行的总体判定与统计。

    第 21 节 Gate 流程：
        Candidate → Vagueness → Definition → TimeWindow → Leak → Barnum →
        Baseline → SelfFulfilling → MultipleTesting → Dependency → Skeptic
    """

    __tablename__ = "adversarial_findings"

    id: Optional[int] = Field(default=None, primary_key=True)
    finding_id: str = Field(unique=True, index=True)
    candidate_id: Optional[str] = Field(default=None, index=True)

    decision: str = Field(index=True, description="PASS / REWRITE / REJECT / EXPERIMENTAL")
    failed_attacks: list[str] = Field(default_factory=list, sa_type=JSON)
    warned_attacks: list[str] = Field(default_factory=list, sa_type=JSON)

    summary: str = Field(default="", sa_column=Column(Text))

    # 第 20.6 节 MultipleTestingAttack 的输入
    candidate_pool_size: Optional[int] = None
    published_count: Optional[int] = None

    created_at: datetime = Field(default_factory=datetime.utcnow)

    # 第 31 节月度审计：CherryPick / Selective Reporting 检测
    audit_month: Optional[str] = Field(default=None, index=True)
