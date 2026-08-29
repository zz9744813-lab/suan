"""对抗性 Gate —— 发布前最后一道防线。

对应工程方案第 21 节：

    Candidate
       ↓ Vagueness
       ↓ Definition
       ↓ Time Window
       ↓ Leak
       ↓ Barnum
       ↓ Baseline
       ↓ Self-Fulfilling
       ↓ Multiple Testing
       ↓ Dependency
       ↓ Skeptic
       ↓
    PASS / REWRITE / REJECT / EXPERIMENTAL

    只有 PASS 可以进入正式 Prediction Ledger。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .attacks.base import AttackContext, AttackOutcome, Verdict
from .attacks.deterministic import ALL_ATTACKS, build_attacks


@dataclass
class GateResult:
    """Gate 运行结论。"""

    decision: str  # PASS / REWRITE / REJECT / EXPERIMENTAL
    outcomes: list[AttackOutcome] = field(default_factory=list)

    @property
    def failed(self) -> list[AttackOutcome]:
        return [o for o in self.outcomes if o.verdict is Verdict.FAIL]

    @property
    def warned(self) -> list[AttackOutcome]:
        return [o for o in self.outcomes if o.verdict is Verdict.WARN]

    def outcome_of(self, attack_name: str) -> AttackOutcome | None:
        for o in self.outcomes:
            if o.attack == attack_name:
                return o
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision,
            "failed": [
                {"attack": o.attack, "reason": o.reason, "severity": o.severity}
                for o in self.failed
            ],
            "warned": [
                {"attack": o.attack, "reason": o.reason, "severity": o.severity}
                for o in self.warned
            ],
        }


# 决定性攻击（FAIL 即 REJECT）
HARD_REJECT = {
    "VaguenessAttack",
    "DefinitionAttack",
    "TimeWindowAttack",
    "OutcomeLeakAttack",
    "RetrofittingAttack",
    "AgentCollusionAttack",
    "NarrativeExcuseAttack",
}

# 需要重写而非直接拒绝的攻击
REWRITE_ON_FAIL = {"BarnumAttack"}


class AdversarialGate:
    """串联 14 种攻击并给出发布决策。"""

    def __init__(self, attacks: list | None = None) -> None:
        self.attacks = attacks or build_attacks()

    def run(self, ctx: AttackContext) -> GateResult:
        outcomes: list[AttackOutcome] = []

        for attack in self.attacks:
            try:
                outcomes.append(attack.run(ctx))
            except Exception as exc:
                # 攻击器自身异常不得放行 —— 记为 WARN 并转人工
                outcomes.append(
                    AttackOutcome(
                        attack=attack.name,
                        verdict=Verdict.WARN,
                        severity=0.8,
                        reason=f"攻击检测器异常：{exc}（保守处理，转人工复核）",
                    )
                )

        failed_names = {o.attack for o in outcomes if o.verdict is Verdict.FAIL}
        warned_names = {o.attack for o in outcomes if o.verdict is Verdict.WARN}

        # ---------- 决策 ----------
        if failed_names & HARD_REJECT:
            decision = "REJECT"
        elif failed_names & REWRITE_ON_FAIL:
            decision = "REWRITE"
        elif failed_names:
            decision = "REJECT"
        elif warned_names & {"VaguenessAttack", "DefinitionAttack"}:
            # 定义层面的警告：必须重写后才能发布
            decision = "REWRITE"
        elif warned_names:
            # 其余警告（巴纳姆、基线、相关证据等）：可发布但标记为实验性
            decision = "EXPERIMENTAL"
        else:
            decision = "PASS"

        return GateResult(decision=decision, outcomes=outcomes)

    @property
    def attack_names(self) -> list[str]:
        return [a.name for a in self.attacks]


def run_gate(ctx: AttackContext) -> GateResult:
    """便捷入口。"""
    return AdversarialGate().run(ctx)


__all__ = ["AdversarialGate", "GateResult", "run_gate", "ALL_ATTACKS", "AttackContext"]
