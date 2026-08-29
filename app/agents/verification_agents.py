"""验证 Agent：OutcomeCollector / OutcomeJudge。

对应工程方案：
- 第 17 节 Outcome Verification
- 第 18 节 部分命中（grading rule 冻结前确定）
- 第 20.13 节 ConfirmationBiasAttack（三方 Judge）
- 第 60 节 用户回复解析
- 第 61 节 现实事件 Journal
- 禁止 3：让 LLM 自己判断自己有没有预测准

第 20.13 节：

    检查 Outcome Judge 是否倾向把模糊现实描述判成「命中」。
    应同时运行：Prosecution Judge / Defense Judge / Neutral Judge
    出现分歧则 NEEDS_USER_CONFIRMATION
"""

from __future__ import annotations

from typing import Any

from app.providers.base import LLMResponse, Tier
from app.schemas.outcome import (
    JudgeRole,
    JudgeVerdict,
    Outcome,
    RealityEvent,
)
from .base import AgentContext, AgentResult, BaseAgent, DeterministicAgent


# ----------------------------------------------------------------------
# OutcomeCollectorAgent（第 60 节）
# ----------------------------------------------------------------------
class OutcomeCollectorAgent(DeterministicAgent):
    """把用户的自然语言回复映射到具体 Prediction。

    第 60 节：
        支持「中了」「没发生」「第二个中了」「差不多算一半」…
        但若可能对应多个预测：必须要求明确对应关系或标记低置信。
        不能强行命中。
    """

    name = "OutcomeCollectorAgent"
    tier = "cheap"

    # 快捷选项映射
    QUICK_MAP = {
        "A": 1.0,
        "B": 0.0,
        "C": 0.5,
        "D": None,  # 无法判断
    }

    def compute(self, ctx: AgentContext) -> dict[str, Any]:
        reply = (ctx.payload.get("user_reply") or "").strip()
        quick = (ctx.payload.get("quick_answer") or "").strip().upper()
        candidates: list[str] = ctx.payload.get("candidate_prediction_ids", [])

        # ---------- 快捷选项优先 ----------
        mapped: float | None = None
        if quick in self.QUICK_MAP:
            mapped = self.QUICK_MAP[quick]

        # ---------- 自然语言：先做确定性关键词解析 ----------
        if mapped is None and reply:
            mapped = self._keyword_outcome(reply)

        # ---------- 歧义检测（第 60 节：不能强行命中）----------
        ambiguous = False
        ambiguity_note = ""
        if len(candidates) > 1 and not self._mentions_index(reply):
            ambiguous = True
            ambiguity_note = (
                f"当前有 {len(candidates)} 条待验证预测，"
                f"用户回复未指明对应哪一条，需要确认（第 60 节）"
            )

        return {
            "parsed_outcome": mapped,
            "ambiguous": ambiguous,
            "ambiguity_note": ambiguity_note,
            "candidate_prediction_ids": candidates,
            "raw_reply": reply,
        }

    @staticmethod
    def _keyword_outcome(reply: str) -> float | None:
        """第 60 节支持的口语表达。确定性规则，不调 LLM。"""
        r = reply.strip()
        if not r:
            return None

        full = {"中了": 1.0, "发生了": 1.0, "有": 1.0, "对": 1.0}
        none = {"没发生": 0.0, "没有": 0.0, "没中": 0.0, "没": 0.0}
        partial = {"差不多算一半": 0.5, "部分": 0.5, "一半": 0.5, "有点": 0.25}
        unknown = {"不知道": None, "无法判断": None, "忘了": None}

        for k, v in unknown.items():
            if k in r:
                return v
        for k, v in full.items():
            if k in r:
                return v
        for k, v in partial.items():
            if k in r:
                return v
        for k, v in none.items():
            if k in r:
                return v
        return None

    @staticmethod
    def _mentions_index(reply: str) -> bool:
        """是否指明了「第 N 条」。"""
        markers = ["第一个", "第二个", "第三个", "第1", "第2", "第3"]
        return any(m in reply for m in markers)

    def build_messages(self, ctx: AgentContext) -> list[dict[str, str]]:
        return []

    def parse_output(self, response: LLMResponse, ctx: AgentContext) -> dict[str, Any]:
        return {}


# ----------------------------------------------------------------------
# OutcomeJudgeAgent（第 17 / 20.13 节）
# ----------------------------------------------------------------------
class OutcomeJudgeAgent(BaseAgent):
    """三方 Judge 判定现实结果。

    第 20.13 节：同时运行 Prosecution / Defense / Neutral，
    防止把模糊现实描述判成「命中」。分歧 → NEEDS_USER_CONFIRMATION。
    """

    name = "OutcomeJudgeAgent"
    tier = Tier = "cheap"  # type: ignore[assignment]
    temperature = 0.2

    ROLE_INSTRUCTION = {
        JudgeRole.PROSECUTION: (
            "你扮演控方。你的职责是严格审查：除非证据明确满足成功标准，"
            "否则倾向判定为「未命中」。模糊描述不算命中。"
        ),
        JudgeRole.DEFENSE: (
            "你扮演辩方。你的职责是识别现实描述中满足成功标准的部分，"
            "但仍须依据冻结时定义的标准，不得事后放宽。"
        ),
        JudgeRole.NEUTRAL: (
            "你扮演中立方。严格依据冻结时定义的成功/失败标准判定，不偏不倚。"
        ),
    }

    def build_messages(self, ctx: AgentContext) -> list[dict[str, str]]:
        role: JudgeRole = ctx.payload["role"]
        pred = ctx.payload.get("prediction", {})
        reply = ctx.payload.get("user_reply", "")
        return [
            {"role": "system", "content": f"{self.system_prompt()}\n\n{self.ROLE_INSTRUCTION[role]}"},
            {
                "role": "user",
                "content": (
                    f"# 冻结时的预测（不得事后修改标准）\n```json\n{pred}\n```\n\n"
                    f"# 用户的现实描述\n{reply}\n\n"
                    f"# 输出要求\n"
                    f"严格输出 JSON：\n"
                    f'{{"outcome": <0.0|0.25|0.5|0.75|1.0>, '
                    f'"confidence": <0.0~1.0>, "reasoning": "..."}}\n\n'
                    f"outcome 只能取这五个值（第 18 节）。"
                ),
            },
        ]

    def parse_output(self, response: LLMResponse, ctx: AgentContext) -> dict[str, Any]:
        data = response.json()
        if not isinstance(data, dict):
            return {"outcome": 0.0, "confidence": 0.0, "reasoning": "输出非 JSON，判为未命中"}

        outcome = float(data.get("outcome", 0.0))
        # 第 18 节：只能落在预定义刻度上
        allowed = (0.0, 0.25, 0.5, 0.75, 1.0)
        outcome = min(allowed, key=lambda x: abs(x - outcome))

        return {
            "outcome": outcome,
            "confidence": max(0.0, min(1.0, float(data.get("confidence", 0.5)))),
            "reasoning": str(data.get("reasoning", "")),
        }

    # ------------------------------------------------------------------
    def judge(
        self, ctx: AgentContext, prediction_id: str, run_ids: dict[str, str] | None = None
    ) -> Outcome:
        """运行三方 Judge 并聚合（第 20.13 节）。"""
        run_ids = run_ids or {}
        verdicts: list[JudgeVerdict] = []

        for role in (JudgeRole.PROSECUTION, JudgeRole.DEFENSE, JudgeRole.NEUTRAL):
            role_ctx = AgentContext(
                user_id=ctx.user_id,
                session=ctx.session,
                target_event=ctx.target_event,
                domain=ctx.domain,
                payload={**ctx.payload, "role": role},
                prediction_id=prediction_id,
            )
            result: AgentResult = self.run(role_ctx)

            if not result.ok:
                # Judge 失败不得默认为命中（第 20.13 节：宁可转人工）
                verdicts.append(
                    JudgeVerdict(
                        prediction_id=prediction_id,
                        role=role,
                        outcome=0.0,
                        confidence=0.0,
                        reasoning=f"Judge 不可用：{result.error}",
                        agent_run_id=result.run_id,
                    )
                )
                continue

            verdicts.append(
                JudgeVerdict(
                    prediction_id=prediction_id,
                    role=role,
                    outcome=result.output["outcome"],
                    confidence=result.output["confidence"],
                    reasoning=result.output["reasoning"],
                    agent_run_id=result.run_id,
                )
            )

        return Outcome.from_verdicts(prediction_id, verdicts)


# ----------------------------------------------------------------------
class RealityEventExtractor(DeterministicAgent):
    """第 61 节：把验证过程中用户提到的现实事件沉淀进 Reality Event Ledger。

    验证不仅为 Prediction 服务，也沉淀 Reality Model 的训练数据。
    """

    name = "RealityEventExtractor"
    tier = "cheap"

    def compute(self, ctx: AgentContext) -> dict[str, Any]:
        payload = ctx.payload
        return {
            "event": RealityEvent(
                user_id=str(ctx.user_id),
                date=payload.get("date"),
                domain=payload.get("domain"),
                event_type=ctx.target_event,
                duration_minutes=payload.get("duration_minutes"),
                magnitude=payload.get("magnitude"),
                source="user_report",
                confidence=payload.get("confidence", 0.95),
                note=payload.get("note", ""),
                prediction_id=ctx.prediction_id,
            ).model_dump(mode="json")
        }

    def build_messages(self, ctx: AgentContext) -> list[dict[str, str]]:
        return []

    def parse_output(self, response: LLMResponse, ctx: AgentContext) -> dict[str, Any]:
        return {}
