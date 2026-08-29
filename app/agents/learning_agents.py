"""学习与审计 Agent：Calibration / Attribution / Learning / Report / Audit。

对应工程方案：
- 第 22 节 Prediction Error Driven Learning
- 第 23 节 失败归因
- 第 24 节 禁止直接在线自修改（Shadow Mode）
- 第 30 节 周报
- 第 31 节 月度模型审计
- 第 32 节 第一性原理审计 Agent
- 第 33 节 Ablation Test
- 第 20.14 节 NarrativeExcuseAttack

第 24 节硬性约束：

    LearningAgent 不能因为一次失败就修改生产规则。
    必须：Production Model → Candidate Rule → Shadow Mode →
          50/100 样本 → Statistical Review → Promote
"""

from __future__ import annotations

from typing import Any

from app.providers.base import LLMResponse, Tier
from .base import AgentContext, BaseAgent, DeterministicAgent


# ----------------------------------------------------------------------
# CalibrationAgent（第 19.3 节）
# ----------------------------------------------------------------------
class CalibrationAgent(DeterministicAgent):
    """概率校准分析与分桶统计。

    第 19.3 节：
        所有标 70% 的预测，实际发生率应该接近 70%。
        如果 90% 实际只发生 76%，说明模型明显过度自信。
    """

    name = "CalibrationAgent"
    tier = "cheap"

    # 分桶边界（第 19.3 节示例：10/30/50/70/90）
    BIN_EDGES = [0.0, 0.2, 0.4, 0.6, 0.8, 1.0]

    def compute(self, ctx: AgentContext) -> dict[str, Any]:
        """输入 scores: [{probability, outcome}]，输出分桶校准表。"""
        scores = ctx.payload.get("scores", [])
        if not scores:
            return {"bins": [], "sample_size": 0, "note": "无样本"}

        bins: list[dict[str, Any]] = []
        for lo, hi in zip(self.BIN_EDGES, self.BIN_EDGES[1:]):
            members = [s for s in scores if lo <= s["probability"] < hi]
            if not members:
                continue
            n = len(members)
            mean_p = sum(s["probability"] for s in members) / n
            mean_y = sum(s["outcome"] for s in members) / n
            bins.append(
                {
                    "bin_lower": lo,
                    "bin_upper": hi,
                    "sample_count": n,
                    "mean_predicted": round(mean_p, 4),
                    "mean_actual": round(mean_y, 4),
                    "calibration_gap": round(mean_y - mean_p, 4),
                }
            )

        # Sharpness（第 19.4 节）：永远预测 50% 虽然校准好但毫无信息
        probs = [s["probability"] for s in scores]
        mean_p = sum(probs) / len(probs)
        sharpness = sum((p - mean_p) ** 2 for p in probs) / len(probs)

        return {
            "bins": bins,
            "sample_size": len(scores),
            "sharpness": round(sharpness, 6),
            "overall_gap": (
                round(sum(s["outcome"] for s in scores) / len(scores) - mean_p, 4)
            ),
        }

    def build_messages(self, ctx: AgentContext) -> list[dict[str, str]]:
        return []

    def parse_output(self, response: LLMResponse, ctx: AgentContext) -> dict[str, Any]:
        return {}


# ----------------------------------------------------------------------
# AttributionAgent（第 23 节）
# ----------------------------------------------------------------------
class AttributionAgent(BaseAgent):
    """失败归因。

    第 20.14 节 NarrativeExcuseAttack 禁止输出：
        「只是应期延后」「能量已经发生」「可能以另一种形式应验」
    除非延迟窗口规则在预测冻结前已注册，否则一律判失败。
    """

    name = "AttributionAgent"
    tier: Tier = "reasoning"
    temperature = 0.3

    def build_messages(self, ctx: AgentContext) -> list[dict[str, str]]:
        pred = ctx.payload.get("prediction", {})
        signals = ctx.payload.get("signals", [])
        return [
            {"role": "system", "content": self.system_prompt()},
            {
                "role": "user",
                "content": (
                    f"# 预测\n```json\n{pred}\n```\n\n"
                    f"# 各源 Signal\n```json\n{signals}\n```\n\n"
                    f"# 输出要求\n"
                    f"严格输出 JSON：\n"
                    f'{{"hypotheses": [{{"id": "H1", "statement": "...", '
                    f'"category": "overconfidence|correlated_evidence|fusion_weight|'
                    f'definition|rule_error|other", '
                    f'"target_system": "...", "target_domain": "...", '
                    f'"target_time_scale": "...", "target_rule_ids": ["..."]}}]}}\n\n'
                    f"每条假设必须指向可对冲的具体对象，禁止笼统归因。"
                ),
            },
        ]

    def parse_output(self, response: LLMResponse, ctx: AgentContext) -> dict[str, Any]:
        data = response.json()
        if not isinstance(data, dict):
            return {"hypotheses": []}
        raw = data.get("hypotheses", [])
        out = []
        for i, h in enumerate(raw if isinstance(raw, list) else [], start=1):
            if not isinstance(h, dict):
                continue
            out.append(
                {
                    "id": str(h.get("id", f"H{i}")),
                    "statement": str(h.get("statement", "")).strip(),
                    "category": str(h.get("category", "other")),
                    "target_system": h.get("target_system"),
                    "target_domain": h.get("target_domain"),
                    "target_time_scale": h.get("target_time_scale"),
                    "target_rule_ids": list(h.get("target_rule_ids", [])),
                }
            )
        return {"hypotheses": [h for h in out if h["statement"]]}

    @staticmethod
    def screen_excuses(statement: str) -> bool:
        """第 20.14 节：检测「叙事性开脱」话术。"""
        banned = ["应期延后", "能量已经发生", "另一种形式应验", "潜在影响", "已经应验了"]
        return any(b in statement for b in banned)


# ----------------------------------------------------------------------
# LearningAgent（第 22 / 24 节）
# ----------------------------------------------------------------------
class LearningAgent(DeterministicAgent):
    """更新可靠度 —— 但绝不能直接改生产规则。

    第 24 节：
        不能因为一次失败就修改生产规则。
        必须走 Shadow Mode → 50/100 样本 → Statistical Review → Promote
    """

    name = "LearningAgent"
    tier = "cheap"

    def compute(self, ctx: AgentContext) -> dict[str, Any]:
        hypotheses = ctx.payload.get("hypotheses", [])
        screened = []
        for h in hypotheses:
            if AttributionAgent.screen_excuses(h.get("statement", "")):
                # 第 20.14 节：叙事性开脱直接丢弃，不进入 Shadow
                continue
            screened.append(h)

        # 生成 Shadow 实验候选（第 24 节）
        experiments = []
        for h in screened:
            experiments.append(
                {
                    "hypothesis_id": h.get("id"),
                    "target_system": h.get("target_system"),
                    "target_domain": h.get("target_domain"),
                    "target_time_scale": h.get("target_time_scale"),
                    "status": "proposed",
                    "target_sample_size": 50,
                    "note": "需走 Shadow Mode，不得直接改生产规则（第 24 节）",
                }
            )

        return {
            "screened_hypotheses": screened,
            "shadow_experiments": experiments,
            "rejected_by_narrative_excuse": len(hypotheses) - len(screened),
        }

    def build_messages(self, ctx: AgentContext) -> list[dict[str, str]]:
        return []

    def parse_output(self, response: LLMResponse, ctx: AgentContext) -> dict[str, Any]:
        return {}


# ----------------------------------------------------------------------
# ReportAgent（第 30 / 31 节）
# ----------------------------------------------------------------------
class ReportAgent(BaseAgent):
    """生成日报 / 周报 / 月报。

    第 30 节周报必须包含：正式预测数 / 可验证 / 不可验证 / Brier /
                        Null Brier / Skill Score / 最佳 / 最弱 / 发现 / 异常 / 建议

    第 51 节：默认必须同时展示成功、失败、部分、无法判断。
             禁止产品设计诱导只看「神预测」。
    """

    name = "ReportAgent"
    tier: Tier = "reasoning"
    temperature = 0.4

    def build_messages(self, ctx: AgentContext) -> list[dict[str, str]]:
        stats = ctx.payload.get("stats", {})
        period = ctx.payload.get("period", "weekly")
        return [
            {"role": "system", "content": self.system_prompt()},
            {
                "role": "user",
                "content": (
                    f"# 周期\n{period}\n\n"
                    f"# 统计数据\n```json\n{stats}\n```\n\n"
                    f"# 输出要求\n"
                    f"严格输出 JSON：\n"
                    f'{{"title": "...", "summary": "...", '
                    f'"highlights": ["..."], "weakest": ["..."], '
                    f'"findings": ["..."], "anomalies": ["..."], '
                    f'"recommendations": ["..."]}}\n\n'
                    f"必须同时报告成功与失败（第 51 节）。\n"
                    f"若样本量不足，必须明确标注「样本不足，结论不可靠」（第 78 节）。"
                ),
            },
        ]

    def parse_output(self, response: LLMResponse, ctx: AgentContext) -> dict[str, Any]:
        data = response.json()
        if not isinstance(data, dict):
            return {"title": "", "summary": "报告生成失败", "highlights": [], "weakest": [],
                    "findings": [], "anomalies": [], "recommendations": []}
        return {
            "title": str(data.get("title", "")),
            "summary": str(data.get("summary", "")),
            "highlights": [str(x) for x in data.get("highlights", [])],
            "weakest": [str(x) for x in data.get("weakest", [])],
            "findings": [str(x) for x in data.get("findings", [])],
            "anomalies": [str(x) for x in data.get("anomalies", [])],
            "recommendations": [str(x) for x in data.get("recommendations", [])],
        }


# ----------------------------------------------------------------------
# FirstPrinciplesAuditAgent（第 32 节）
# ----------------------------------------------------------------------
class FirstPrinciplesAuditAgent(BaseAgent):
    """月度第一性原理审计。第 32 节强制提出的 10 个问题。"""

    name = "FirstPrinciplesAuditAgent"
    tier: Tier = "reasoning"
    temperature = 0.3

    AUDIT_QUESTIONS = [
        "当前系统真的预测到了什么？",
        "哪些结果只是基础概率？",
        "哪些结果可能来自现实数据而不是术数？",
        "如果移除紫微，性能下降多少？",
        "如果移除八字，性能下降多少？",
        "如果只保留 Reality，性能怎样？",
        "当前最可能是伪相关的规则是什么？",
        "哪些规则已经连续失败？",
        "哪些所谓「命中」实际上定义模糊？",
        "系统有没有通过解释而不是预测获得虚假成功？",
    ]

    def build_messages(self, ctx: AgentContext) -> list[dict[str, str]]:
        stats = ctx.payload.get("stats", {})
        questions = "\n".join(f"{i+1}. {q}" for i, q in enumerate(self.AUDIT_QUESTIONS))
        return [
            {"role": "system", "content": self.system_prompt()},
            {
                "role": "user",
                "content": (
                    f"# 月度审计\n\n# 统计数据\n```json\n{stats}\n```\n\n"
                    f"# 必须逐条回答的问题\n{questions}\n\n"
                    f"# 输出要求\n"
                    f"严格输出 JSON：\n"
                    f'{{"answers": [{{"question": "...", "answer": "...", '
                    f'"evidence": "...", "severity": "info|warn|critical"}}], '
                    f'"verdict": "..."}}\n\n'
                    f"要求：结论必须由数据支撑，不得用形容词代替证据。"
                ),
            },
        ]

    def parse_output(self, response: LLMResponse, ctx: AgentContext) -> dict[str, Any]:
        data = response.json()
        if not isinstance(data, dict):
            return {"answers": [], "verdict": "审计生成失败"}
        raw = data.get("answers", [])
        answers = [
            {
                "question": str(a.get("question", "")),
                "answer": str(a.get("answer", "")),
                "evidence": str(a.get("evidence", "")),
                "severity": str(a.get("severity", "info")),
            }
            for a in (raw if isinstance(raw, list) else [])
            if isinstance(a, dict)
        ]
        return {"answers": answers, "verdict": str(data.get("verdict", ""))}
