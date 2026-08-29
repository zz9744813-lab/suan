"""AdversarialAgent —— 执行攻击测试并落库。

对应工程方案：
- 第 20 节 对抗性审查系统
- 第 21 节 对抗性 Gate
- 第 39 节 adversarial_tests 表

第 20 节开宗明义：这是核心基础设施，不是附属 Agent。
本 Agent 只做编排与落库，检测逻辑全部在 app/adversarial/ 下，
且全部为确定性实现（不依赖 LLM）。
"""

from __future__ import annotations

from typing import Any

from app.adversarial.attacks.base import AttackContext
from app.adversarial.gate import AdversarialGate, GateResult
from app.models.adversarial import AdversarialFinding, AdversarialTest
from app.providers.base import LLMResponse

from .base import AgentContext, DeterministicAgent


class AdversarialAgent(DeterministicAgent):
    """运行 14 种攻击 + Gate，并把每条结果写入 adversarial_tests。"""

    name = "AdversarialAgent"
    tier = "cheap"

    def compute(self, ctx: AgentContext) -> dict[str, Any]:
        payload = ctx.payload
        attack_ctx: AttackContext = payload.get("attack_context")
        if attack_ctx is None:
            raise ValueError("payload 必须提供 attack_context（AttackContext）")

        gate: AdversarialGate = payload.get("gate") or AdversarialGate()
        result: GateResult = gate.run(attack_ctx)

        candidate_id = payload.get("candidate_id") or ctx.prediction_candidate_id
        prediction_id = payload.get("prediction_id") or ctx.prediction_id

        # ---------- 落库：逐条攻击结果 ----------
        for o in result.outcomes:
            ctx.session.add(
                AdversarialTest(
                    candidate_id=candidate_id,
                    prediction_id=prediction_id,
                    attack_type=o.attack,
                    result=o.verdict.value,
                    severity=o.severity,
                    reason=o.reason,
                    details=o.details or {},
                )
            )
        ctx.session.commit()

        # ---------- 落库：总体结论 ----------
        import uuid

        finding = AdversarialFinding(
            finding_id=f"F-{uuid.uuid4().hex[:12]}",
            candidate_id=candidate_id,
            decision=result.decision,
            failed_attacks=[o.attack for o in result.failed],
            warned_attacks=[o.attack for o in result.warned],
            summary=self._summarize(result),
            candidate_pool_size=attack_ctx.candidate_pool_size,
            published_count=attack_ctx.published_count,
        )
        ctx.session.add(finding)
        ctx.session.commit()

        return {
            "decision": result.decision,
            "failed_attacks": finding.failed_attacks,
            "warned_attacks": finding.warned_attacks,
            "summary": finding.summary,
            "finding_id": finding.finding_id,
            "details": result.to_dict(),
        }

    @staticmethod
    def _summarize(result: GateResult) -> str:
        if result.decision == "PASS":
            return "通过全部 14 项对抗性检测"
        parts = []
        if result.failed:
            parts.append("失败：" + "、".join(f"{o.attack}（{o.reason}）" for o in result.failed))
        if result.warned:
            parts.append("警告：" + "、".join(f"{o.attack}（{o.reason}）" for o in result.warned))
        return f"决策 {result.decision} —— " + "；".join(parts)

    def build_messages(self, ctx: AgentContext) -> list[dict[str, str]]:
        return []

    def parse_output(self, response: LLMResponse, ctx: AgentContext) -> dict[str, Any]:
        return {}
