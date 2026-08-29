"""预测管线 Agent：FutureScanner / Candidate / Skeptic / Freeze。

对应工程方案：
- 第 3 节 系统主动预测能力（系统不等待用户提问）
- 第 3.2 节 Future Scanner（寻找值得预测的事，而不是直接预测）
- 第 4.3 节 Information Value
- 第 13 节 Agent 体系
- 第 16 节 Prediction Pre-registration
- 第 18 节 部分命中（grading rule 必须冻结前确定）
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from app.providers.base import LLMResponse, Tier
from app.schemas.prediction import (
    InformationValue,
    Prediction,
    PredictionCandidate,
)
from app.schemas.signal import Domain, TimeScale, TimeWindow

from .base import AgentContext, AgentResult, BaseAgent, DeterministicAgent
from ..prediction.ontology import ONTOLOGY, by_scale


# ----------------------------------------------------------------------
# FutureScannerAgent（第 3.2 节）
# ----------------------------------------------------------------------
class FutureScannerAgent(BaseAgent):
    """生成待预测目标。

    第 3.2 节：
        Future Scanner 负责寻找值得预测的事情，而不是直接预测。
        候选 ≠ 正式预测。

    每天生成候选（方案示例为 50 个）。LLM 不可用时回落 Event Ontology。
    """

    name = "FutureScannerAgent"
    tier: Tier = "reasoning"
    temperature: float = 0.7

    def build_messages(self, ctx: AgentContext) -> list[dict[str, str]]:
        scale = ctx.payload.get("time_scale", "day")
        ontology_hint = [s.event_type for s in by_scale(scale)][:40]
        state = ctx.payload.get("reality_state", {})
        return [
            {"role": "system", "content": self.system_prompt()},
            {
                "role": "user",
                "content": (
                    f"# 任务\n"
                    f"时间尺度：{scale}\n"
                    f"目标日期：{ctx.payload.get('target_date', 'today')}\n\n"
                    f"# 用户近期现实状态\n```json\n{state}\n```\n\n"
                    f"# 候选事件类型（优先复用，避免你自创说法）\n"
                    f"{ontology_hint}\n\n"
                    f"# 输出要求\n"
                    f"严格输出 JSON：\n"
                    f'{{"candidates": [{{"event_type": "...", "domain": "...", '
                    f'"description": "...", "why_falsifiable": "..."}}]}}\n\n'
                    f"要求：每条都可观测、可记录、有明确判定方式。\n"
                    f"禁止输出「心情变好」「运势上升」这类无法观测的内容。"
                ),
            },
        ]

    def parse_output(self, response: LLMResponse, ctx: AgentContext) -> dict[str, Any]:
        data = response.json()
        if not isinstance(data, dict):
            return {"candidates": [], "source": "fallback", "error": "输出非 JSON"}

        raw = data.get("candidates", [])
        out = []
        for item in raw if isinstance(raw, list) else []:
            if not isinstance(item, dict):
                continue
            event_type = str(item.get("event_type", "")).strip()
            if not event_type:
                continue
            out.append(
                {
                    "event_type": event_type,
                    "domain": str(item.get("domain", "")).strip() or event_type.split(".")[0],
                    "description": str(item.get("description", "")).strip(),
                    "why_falsifiable": str(item.get("why_falsifiable", "")).strip(),
                }
            )
        return {"candidates": out, "source": "llm"}

    def scan(self, ctx: AgentContext, limit: int = 50) -> list[dict[str, Any]]:
        """执行扫描。LLM 不可用时回落 Event Ontology（保证管线不中断）。"""
        result = self.run(ctx)
        cands = result.output.get("candidates", [])
        if cands:
            return cands[:limit]

        # 回落：直接从 Ontology 取适用尺度（第 56 节：避免 LLM 自创说法）
        scale = ctx.payload.get("time_scale", "day")
        return [
            {
                "event_type": spec.event_type,
                "domain": spec.domain,
                "description": spec.label,
                "why_falsifiable": "；".join(spec.success_criteria),
                "source": "ontology_fallback",
            }
            for spec in by_scale(scale)[:limit]
        ]


# ----------------------------------------------------------------------
# CandidateAgent（第 13 节：生成可验证预测候选）
# ----------------------------------------------------------------------
class CandidateAgent(BaseAgent):
    """把扫描到的目标 + 各方 Signal 转成可验证的预测候选。

    第 18 节硬性要求：
        每一种预测的 grading rule 必须在预测冻结前确定。
        不能事后调整评分规则。
    """

    name = "CandidateAgent"
    tier: Tier = "reasoning"
    temperature: float = 0.4

    def build_messages(self, ctx: AgentContext) -> list[dict[str, str]]:
        spec = ONTOLOGY.get(ctx.target_event)
        base_criteria = list(spec.success_criteria) if spec else []
        base_failure = list(spec.failure_criteria) if spec else []
        return [
            {"role": "system", "content": self.system_prompt()},
            {
                "role": "user",
                "content": (
                    f"# 任务\n"
                    f"事件类型：{ctx.target_event}\n"
                    f"领域：{ctx.domain}\n"
                    f"时间窗口：{ctx.payload.get('window_text', '')}\n"
                    f"Null 基线概率：{ctx.payload.get('null_probability', 0.5)}\n\n"
                    f"# 参考标准（可细化，不得放宽）\n"
                    f"成功：{base_criteria}\n"
                    f"失败：{base_failure}\n\n"
                    f"# 输出要求\n"
                    f"严格输出 JSON：\n"
                    f'{{"description": "...", "probability": <0.0~1.0>, '
                    f'"success_criteria": ["..."], "failure_criteria": ["..."], '
                    f'"grading_rule": "...", "abstain": <true/false>}}\n\n'
                    f"成功与失败标准必须是可观测的事实陈述，不得含「可能」「大概」。"
                ),
            },
        ]

    def parse_output(self, response: LLMResponse, ctx: AgentContext) -> dict[str, Any]:
        data = response.json()
        if not isinstance(data, dict):
            return {"abstain": True, "error": "输出非 JSON"}
        if data.get("abstain"):
            return {"abstain": True, "reason": data.get("reason", "Agent 放弃")}

        probability = float(data.get("probability", ctx.payload.get("null_probability", 0.5)))
        probability = max(0.01, min(0.99, probability))

        success = [str(x) for x in data.get("success_criteria", []) if str(x).strip()]
        failure = [str(x) for x in data.get("failure_criteria", []) if str(x).strip()]
        if not success or not failure:
            # C-001：无法证伪的预测不允许进入候选
            return {"abstain": True, "reason": "成功/失败标准缺失（C-001 可证伪原则）"}

        return {
            "description": str(data.get("description", ctx.target_event)),
            "probability": probability,
            "success_criteria": success,
            "failure_criteria": failure,
            "grading_rule": str(data.get("grading_rule", "二值：发生=1.0，未发生=0.0")),
        }

    def build_candidate(
        self,
        ctx: AgentContext,
        *,
        window: TimeWindow,
        time_scale: TimeScale = TimeScale.DAY,
        signals: list[Any] | None = None,
    ) -> PredictionCandidate | None:
        """构造候选。Agent 放弃时返回 None。"""
        result = self.run(ctx)
        if not result.ok or result.output.get("abstain"):
            return None

        spec = ONTOLOGY.get(ctx.target_event)
        domain = Domain(ctx.domain) if ctx.domain in Domain._value2member_map_ else (
            spec.domain if False else Domain.UNEXPECTED_EVENT
        )

        return PredictionCandidate(
            domain=domain,
            event_type=ctx.target_event,
            description=result.output["description"],
            probability=result.output["probability"],
            time_scale=time_scale,
            window_start=window.start,
            window_end=window.end,
            success_criteria=result.output["success_criteria"],
            failure_criteria=result.output["failure_criteria"],
            grading_rule=result.output["grading_rule"],
            signals=list(signals or []),
        )


# ----------------------------------------------------------------------
# SkepticAgent（第 13 节：反对当前结论）
# ----------------------------------------------------------------------
class SkepticAgent(BaseAgent):
    """反对当前结论。

    第 21 节 Gate 的最后一环；第 20.10 节 BaselineAttack 的人工增强版。
    """

    name = "SkepticAgent"
    tier: Tier = "reasoning"
    temperature: float = 0.6

    def build_messages(self, ctx: AgentContext) -> list[dict[str, str]]:
        cand = ctx.payload.get("candidate", {})
        return [
            {"role": "system", "content": self.system_prompt()},
            {
                "role": "user",
                "content": (
                    f"# 待审查的候选预测\n```json\n{cand}\n```\n\n"
                    f"# 输出要求\n"
                    f"严格输出 JSON：\n"
                    f'{{"objections": ["..."], "is_baseline_only": <true/false>, '
                    f'"definition_too_broad": <true/false>, '
                    f'"suggested_probability": <0.0~1.0 或 null>}}\n\n'
                    f"如果你找不到任何反对理由，如实输出空 objections，"
                    f"不要为了反对而反对。"
                ),
            },
        ]

    def parse_output(self, response: LLMResponse, ctx: AgentContext) -> dict[str, Any]:
        data = response.json()
        if not isinstance(data, dict):
            return {"objections": [], "is_baseline_only": False, "definition_too_broad": False}
        return {
            "objections": [str(x) for x in data.get("objections", [])],
            "is_baseline_only": bool(data.get("is_baseline_only", False)),
            "definition_too_broad": bool(data.get("definition_too_broad", False)),
            "suggested_probability": data.get("suggested_probability"),
        }


# ----------------------------------------------------------------------
# FreezeAgent（第 16 节：预测预注册）—— 纯确定性
# ----------------------------------------------------------------------
class FreezeAgent(DeterministicAgent):
    """预测预注册与冻结。

    第 16 节：冻结时保存 prediction / probability / time_window /
    success_criteria / failure_criteria / all_signals / all_agent_outputs /
    input_snapshot / model / provider / prompt_version / rule_version /
    engine_version / timestamp / sha256

    冻结后：UPDATE 原文 = 禁止。
    """

    name = "FreezeAgent"
    tier = "cheap"

    def compute(self, ctx: AgentContext) -> dict[str, Any]:
        from app.config import get_settings

        settings = get_settings()
        payload = ctx.payload

        prediction: Prediction = payload["prediction"]
        prediction.model_version = settings.MODEL_VERSION
        prediction.fusion_version = settings.FUSION_VERSION
        prediction.prompt_version = settings.PROMPT_VERSION
        prediction.rule_version = settings.RULE_VERSION
        prediction.engine_version = settings.ENGINE_VERSION
        prediction.freeze()

        return {
            "prediction_id": prediction.prediction_id,
            "sha256": prediction.prediction_hash,
            "frozen_at": prediction.frozen_at.isoformat() if prediction.frozen_at else None,
            "status": prediction.status.value,
        }

    @staticmethod
    def default_window(
        target_date: datetime, time_scale: TimeScale = TimeScale.DAY
    ) -> TimeWindow:
        """按尺度生成默认窗口。第 20.4 节：必须有明确时间窗口。"""
        start = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
        spans = {
            TimeScale.DAY: timedelta(days=1),
            TimeScale.WEEK: timedelta(days=7),
            TimeScale.MONTH: timedelta(days=30),
            TimeScale.YEAR: timedelta(days=365),
        }
        end = start + spans.get(time_scale, timedelta(days=1)) - timedelta(seconds=1)
        return TimeWindow(start=start, end=end)
