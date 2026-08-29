"""对抗性 Attack 基类。

对应工程方案第 20 节：

    这是核心基础设施，不是附属 Agent。

第 21 节 Gate 流程：
    Candidate → Vagueness → Definition → TimeWindow → Leak → Barnum →
    Baseline → SelfFulfilling → MultipleTesting → Dependency → Skeptic

    结果：PASS / REWRITE / REJECT / EXPERIMENTAL
    只有 PASS 可以进入正式 Prediction Ledger。

设计原则：
    14 种攻击全部提供确定性实现（不依赖 LLM）。
    原因：对抗性审查是系统的最后防线，它本身不能再依赖一个
    会产生幻觉的组件。LLM 版本可作为增强，但绝不能是唯一实现。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Verdict(str, Enum):
    """单项攻击结论。"""

    PASS = "PASS"
    FAIL = "FAIL"
    WARN = "WARN"
    SKIP = "SKIP"


@dataclass
class AttackOutcome:
    """一次攻击的结果。"""

    attack: str
    verdict: Verdict
    severity: float = 0.0          # 0.0 ~ 1.0
    reason: str = ""
    details: dict[str, Any] = field(default_factory=dict)

    @property
    def failed(self) -> bool:
        return self.verdict is Verdict.FAIL


@dataclass
class AttackContext:
    """攻击输入。宽松结构：各 Attack 按需取用。

    字段缺失时 Attack 应返回 SKIP，而不是崩溃或误判。
    """

    # 待审查对象
    description: str = ""
    event_type: str = ""
    probability: float | None = None
    null_probability: float | None = None
    success_criteria: list[str] = field(default_factory=list)
    failure_criteria: list[str] = field(default_factory=list)
    window_start: Any = None
    window_end: Any = None
    grading_rule: str = ""

    # 信号与证据
    signals: list[dict[str, Any]] = field(default_factory=list)
    dependency_groups: dict[str, list[str]] = field(default_factory=dict)

    # Agent 相关（第 20.11 节 collusion 检测）
    agent_texts: dict[str, str] = field(default_factory=dict)
    agent_runs_saw_others: list[bool] = field(default_factory=list)

    # 完整性（第 20.7 节）
    prediction_hash: str | None = None
    recomputed_hash: str | None = None

    # 输入快照（第 20.8 节 leak 检测）
    input_snapshot: dict[str, Any] = field(default_factory=dict)
    created_at: Any = None
    window_started: bool = False

    # 多重检验（第 20.6 节）
    candidate_pool_size: int | None = None
    published_count: int | None = None

    # 结果判定（第 20.13 节）
    judge_verdicts: list[dict[str, Any]] = field(default_factory=list)

    # 验证后文本（第 20.14 节）
    post_hoc_statements: list[str] = field(default_factory=list)

    # 用户可见性（第 20.9 节）
    visibility_mode: str = "VISIBLE"
    # 该事件是否容易被「看到预测后主动去做」影响
    self_fulfillable_event_types: set[str] = field(default_factory=set)


class Attack(ABC):
    """攻击检测器基类。"""

    name: str = "Attack"
    # 失败是否直接 REJECT（否则为 REWRITE / 降权）
    blocking: bool = True

    @abstractmethod
    def run(self, ctx: AttackContext) -> AttackOutcome:
        """执行检测。数据不足时返回 SKIP。"""

    # 便捷构造器。
    # 注意：details 是显式 dict 参数，不是 **kwargs —— 否则调用方写
    # `details={...}` 会被 kwargs 捕获成 {"details": {...}}，造成双层嵌套。
    def _pass(self, reason: str = "", details: dict[str, Any] | None = None) -> AttackOutcome:
        return AttackOutcome(self.name, Verdict.PASS, 0.0, reason, details or {})

    def _fail(
        self, reason: str, severity: float = 1.0, details: dict[str, Any] | None = None
    ) -> AttackOutcome:
        return AttackOutcome(
            self.name, Verdict.FAIL, min(1.0, max(0.0, severity)), reason, details or {}
        )

    def _warn(
        self, reason: str, severity: float = 0.5, details: dict[str, Any] | None = None
    ) -> AttackOutcome:
        return AttackOutcome(
            self.name, Verdict.WARN, min(1.0, max(0.0, severity)), reason, details or {}
        )

    def _skip(self, reason: str = "数据不足") -> AttackOutcome:
        return AttackOutcome(self.name, Verdict.SKIP, 0.0, reason)
