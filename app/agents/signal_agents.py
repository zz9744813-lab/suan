"""信号层 Agent：七个术式解释 Agent + RealityAgent + NullAgent。

对应工程方案：
- 第 13 节 Agent 体系
- 第 6.1 节：程序负责排盘，LLM 负责断卦/解释
- 第 14 节：输出必须是结构化 Signal，禁止自然语言进入 Fusion
- 第 10 节 Reality Engine
- 第 11 节 Null Model

关键分工：
    Adapter（app/core/*）  → deterministic 排盘 + 传统规则映射
    *Agent（本文件）      → 基于排盘的 LLM 解释，输出仍是结构化 Signal

若 LLM 不可用，Agent 回落为 Adapter 的 deterministic Signal，
绝不用 LLM 编造排盘（第 6.1 节）。
"""

from __future__ import annotations

from typing import Any

from app.core.base import AdapterQuery, registry as adapter_registry
from app.providers.base import LLMResponse, Tier
from app.schemas.signal import (
    Evidence,
    EvidenceSource,
    Signal,
    SourceType,
    TimeScale,
    TimeWindow,
)
from .base import AgentContext, AgentResult, BaseAgent, DeterministicAgent


class MetaphysicalAgent(BaseAgent):
    """术式解释 Agent 基类。

    输入：Adapter 的排盘结果（deterministic）
    输出：统一 Signal（结构化）
    """

    source: SourceType = SourceType.BAZI
    tier: Tier = "reasoning"
    temperature: float = 0.3

    def build_messages(self, ctx: AgentContext) -> list[dict[str, str]]:
        chart = ctx.payload.get("chart", {})
        return [
            {"role": "system", "content": self.system_prompt()},
            {
                "role": "user",
                "content": (
                    f"# 任务\n"
                    f"目标事件：{ctx.target_event}\n"
                    f"领域：{ctx.domain}\n"
                    f"时间尺度：{ctx.payload.get('time_scale', 'day')}\n\n"
                    f"# 已排好的盘（由确定性程序计算，你不得自行改算）\n"
                    f"```json\n{_summarize_chart(self.source, chart)}\n```\n\n"
                    f"# 输出要求\n"
                    f"严格输出 JSON：\n"
                    f'{{"direction": <-1.0~1.0>, "strength": <0.0~1.0>, '
                    f'"confidence": <0.0~1.0>, "evidence": ["..."], '
                    f'"counter_evidence": ["..."], "rule_ids": ["..."], '
                    f'"abstain": <true/false>}}\n\n'
                    f"若信息不足以判断，输出 abstain=true 并把 confidence 设为 0。"
                ),
            },
        ]

    def parse_output(self, response: LLMResponse, ctx: AgentContext) -> dict[str, Any]:
        data = response.json()
        if not isinstance(data, dict):
            return {"abstain": True, "reason": "输出非 JSON"}

        if data.get("abstain"):
            return {"abstain": True, "reason": data.get("reason", "Agent 主动放弃预测")}

        return {
            "direction": float(data.get("direction", 0.0)),
            "strength": float(data.get("strength", 0.0)),
            "confidence": float(data.get("confidence", 0.0)),
            "evidence": list(data.get("evidence", [])),
            "counter_evidence": list(data.get("counter_evidence", [])),
            "rule_ids": list(data.get("rule_ids", [])),
        }

    def to_signal(self, ctx: AgentContext, result: AgentResult) -> Signal:
        """AgentResult → Signal。Agent 放弃时返回 degraded Signal。"""
        if not result.ok or result.output.get("abstain"):
            return Signal(
                source=self.source,
                domain=_domain_of(ctx),
                target_event=ctx.target_event,
                direction=0.0,
                strength=0.0,
                confidence=0.0,
                time_window=ctx.payload["window"],
                time_scale=ctx.payload.get("time_scale", TimeScale.DAY),
                degraded=True,
                degrade_reason=result.error or result.output.get("reason", "Agent 放弃预测"),
            )

        return Signal(
            source=self.source,
            domain=_domain_of(ctx),
            target_event=ctx.target_event,
            direction=_clamp(result.output.get("direction", 0.0), -1.0, 1.0),
            strength=_clamp(result.output.get("strength", 0.0), 0.0, 1.0),
            confidence=_clamp(result.output.get("confidence", 0.0), 0.0, 1.0),
            time_window=ctx.payload["window"],
            time_scale=ctx.payload.get("time_scale", TimeScale.DAY),
            evidence=[
                Evidence(
                    # 第 55 节：LLM 的解释必须标记为 LLM_INFERENCE，
                    # 不得伪装成 TRADITIONAL_RULE
                    source=EvidenceSource.LLM_INFERENCE,
                    rule_id=rid,
                    description=text,
                )
                for rid, text in _zip_rules(
                    result.output.get("evidence", []), result.output.get("rule_ids", [])
                )
            ],
            counter_evidence=[
                Evidence(
                    source=EvidenceSource.LLM_INFERENCE,
                    description=text,
                )
                for text in result.output.get("counter_evidence", [])
            ],
            rule_ids=list(result.output.get("rule_ids", [])),
            # 第 20.12 节：历法类术式共享同一依赖组，Fusion 会去相关
            dependency_group=(
                "lunar_calendar"
                if self.source
                in {SourceType.ZIWEI, SourceType.BAZI, SourceType.QIMEN, SourceType.MEIHUA}
                else None
            ),
            engine_version=ctx.payload.get("engine_version", "unknown"),
            prompt_version=ctx.payload.get("prompt_version"),
        )


class ZiweiAgent(MetaphysicalAgent):
    """第 13 节：紫微信号解释。"""

    name = "ZiweiAgent"
    source = SourceType.ZIWEI


class BaziAgent(MetaphysicalAgent):
    """第 13 节：八字信号解释。"""

    name = "BaziAgent"
    source = SourceType.BAZI


class QimenAgent(MetaphysicalAgent):
    """第 13 节：奇门信号解释。"""

    name = "QimenAgent"
    source = SourceType.QIMEN


class LiuyaoAgent(MetaphysicalAgent):
    """第 13 节：六爻解释。"""

    name = "LiuyaoAgent"
    source = SourceType.LIUYAO


class MeihuaAgent(MetaphysicalAgent):
    """第 13 节：梅花解释。"""

    name = "MeihuaAgent"
    source = SourceType.MEIHUA


class PalmAgent(MetaphysicalAgent):
    """第 13 节：掌纹传统映射。第 8 节：消费 PalmFeatures，不是原图。"""

    name = "PalmAgent"
    source = SourceType.PALM
    tier = "vision"


class FaceAgent(MetaphysicalAgent):
    """第 13 节：面相传统映射。

    第 9 节禁止：不得推断医疗、智力、犯罪倾向、政治立场、种族、性取向。
    """

    name = "FaceAgent"
    source = SourceType.FACE
    tier = "vision"


# ----------------------------------------------------------------------
# RealityAgent（第 10 节）
# ----------------------------------------------------------------------
class RealityAgent(MetaphysicalAgent):
    """第 13 节：现实条件分析。

    与术式 Agent 的区别：输入是 RealityState / 用户计划 / 近期行为，
    不含任何术数内容。第 7 节 V2 传统模块之外的现实信号。
    """

    name = "RealityAgent"
    source = SourceType.REALITY

    def build_messages(self, ctx: AgentContext) -> list[dict[str, str]]:
        state = ctx.payload.get("reality_state", {})
        return [
            {"role": "system", "content": self.system_prompt()},
            {
                "role": "user",
                "content": (
                    f"# 任务\n"
                    f"目标事件：{ctx.target_event}\n"
                    f"领域：{ctx.domain}\n\n"
                    f"# 用户近期现实状态（来自日记/任务/消费/日程统计）\n"
                    f"```json\n{state}\n```\n\n"
                    f"# 约束\n"
                    f"你只能使用上述现实数据、历史规律与常识。\n"
                    f"禁止引用任何术数、命理、运势概念（第 11 节：Reality 不含术数）。\n\n"
                    f"# 输出要求\n"
                    f"严格输出 JSON，键同术式 Agent。"
                ),
            },
        ]


# ----------------------------------------------------------------------
# NullAgent（第 11 节）—— 纯确定性，不调用 LLM
# ----------------------------------------------------------------------
class NullAgent(DeterministicAgent):
    """第 11 节 Null Model：完全不知道任何术数的基线预测模型。

    只允许使用：历史事件频率 / 星期 / 工作日 / 已知日程 /
                用户计划 / 近期行为 / 时间序列 / 简单统计

    这是判断「术数到底有没有增量信息」的唯一标尺（第 84 节 North Star）。
    """

    name = "NullAgent"
    tier = "cheap"

    def compute(self, ctx: AgentContext) -> dict[str, Any]:
        from app.reality.null_model import NullModel

        window: TimeWindow | None = ctx.payload.get("window")
        model = NullModel(ctx.session)
        est = model.base_rate(
            user_id=ctx.user_id,
            event_type=ctx.target_event,
            weekday=window.start.weekday() if window else None,
        )
        return {
            "probability": est.probability,
            "raw_rate": est.raw_rate,
            "sample_size": est.sample_size,
            "reliability": est.reliability,
            "note": est.note,
        }

    def signal(self, ctx: AgentContext) -> Signal:
        """Null 基线概率 → Signal（direction 恒为 0）。"""
        from app.reality.null_model import NullModel

        model = NullModel(ctx.session)
        return model.signal(
            user_id=ctx.user_id,
            event_type=ctx.target_event,
            domain=_domain_of(ctx),
            window=ctx.payload["window"],
            time_scale=ctx.payload.get("time_scale", TimeScale.DAY),
        )


# ----------------------------------------------------------------------
def run_adapter(query: AdapterQuery) -> list[Signal]:
    """运行对应术式的 Adapter（deterministic 部分）。"""
    adapter = adapter_registry.get(query.domain and _source_from_query(query))
    if adapter is None:
        return []
    return adapter.signals(query)


# ----------------------------------------------------------------------
def _domain_of(ctx: AgentContext):
    from app.schemas.signal import Domain

    try:
        return Domain(ctx.domain)
    except ValueError:
        return Domain.UNEXPECTED_EVENT


def _summarize_chart(source: SourceType, chart: dict) -> dict:
    """精简排盘结果，只保留关键字段给 LLM。

    背景：实测 qiyovo 中转站对 >1k token 的请求会挂起超时（90s+）。
    全量 chart（八字大运/奇门九宫/紫微 12 宫）太大，必须摘要。
    排盘的确定性结果已在 Adapter 层转成 Signal；LLM 只做增强解读。
    """
    if not chart:
        return {}

    # 八字：四柱 + 十神（干/支）+ 五行，砍掉大运全量
    if source in (SourceType.BAZI,):
        return {
            k: chart.get(k)
            for k in ("bazi", "shishen", "shishen_zhi", "bazi_wuxing", "ming_gong", "liunian")
            if k in chart
        }

    # 六爻/梅花：本卦/变卦/体用/动爻
    if source in (SourceType.LIUYAO, SourceType.MEIHUA):
        out = {k: chart.get(k) for k in (
            "ben_gua", "bian_gua", "ti_gua", "yong_gua",
            "ti_wuxing", "yong_wuxing", "relation", "moving_yao",
            "xunkong", "shi_yao_index", "ying_yao_index",
        ) if k in chart}
        # 六爻逐爻只保留关键列
        if "yao_details" in chart:
            out["yao_details"] = [
                {k: y.get(k) for k in ("position", "liuqin", "branch", "wuxing", "moving", "score")}
                for y in chart["yao_details"]
            ]
        return out

    # 奇门：遁局/值符/门星（九宫只留非中宫的关键列）
    if source is SourceType.QIMEN:
        out = {k: chart.get(k) for k in (
            "dun_type", "ju_number", "yuan", "zhifu", "active_jie",
            "time_stem_visible", "detected_patterns",
        ) if k in chart}
        out["palaces"] = [
            {k: p.get(k) for k in ("palace", "name", "door", "star", "sky_stem", "god")}
            for p in (chart.get("palaces") or []) if not p.get("is_center")
        ]
        return out

    # 紫微：命宫 + 目标宫主星（12 宫全量太大）
    if source is SourceType.ZIWEI:
        return {
            "soul_palace": chart.get("soul_palace"),
            "soul_major_stars": chart.get("soul_major_stars"),
            "palaces": [
                {"name": p.get("name"), "stars": [
                    {k: s.get(k) for k in ("name", "label", "brightness", "mutagen")}
                    for s in (p.get("major_stars") or [])
                ]}
                for p in (chart.get("palaces") or [])
            ],
        }

    # 兜底：截断到 1500 字符
    import json as _json

    text = _json.dumps(chart, ensure_ascii=False)
    if len(text) > 1500:
        import json as _json2

        keys = list(chart.keys())[:6]
        return {k: chart[k] for k in keys}
    return chart


def _source_from_query(query: AdapterQuery) -> SourceType:
    return SourceType.BAZI  # 骨架默认；完整实现按 query 指定术式


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _zip_rules(evidence: list[str], rule_ids: list[str]):
    """把 evidence 文本与 rule_id 配对；rule_id 不足时留空。"""
    out = []
    for i, text in enumerate(evidence):
        out.append((rule_ids[i] if i < len(rule_ids) else "", str(text)))
    return out
