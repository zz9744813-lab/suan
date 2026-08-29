"""FusionAgent —— 独立信号聚合。

对应工程方案：
- 第 12 节 Blind Multi-Agent
- 第 20.12 节 CorrelatedEvidenceAttack
- 第 26 节 Personal Reliability Matrix
- 第 57 节 时间尺度约束
- 禁止 6：初始只允许弱先验，长期由实证数据学习

第 20.12 节核心洞察：

    紫微、八字、黄历等可能共享同类历法信号。
    不能因为「4 个术式支持」就错误理解成「4 个独立证据」。

    建立 Evidence Dependency Graph，降低相关证据重复计权。

融合分两步：
    1. 组内合并：同一 dependency_group 的信号视为同源，取加权平均（不叠加）
    2. 组间融合：不同组之间才做独立加权平均

禁止 2：
    把所有专家报告一起交给 LLM，然后让它「综合判断」。
    必须先结构化 Signal —— 本 Agent 消费的是 Signal，不是文本报告。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.schemas.signal import Signal, TimeScale

# 融合强度：术数信号相对 Null 基线的最大偏移幅度。
# 禁止 6：初始只允许弱先验 —— 因此取值保守，长期由实证数据学习。
DEFAULT_FUSION_ALPHA = 0.18

# 单信号最小有效权重：低于此值的信号不参与融合（噪声抑制）
MIN_EFFECTIVE_WEIGHT = 0.01


@dataclass
class FusionInput:
    signals: list[Signal] = field(default_factory=list)
    null_probability: float = 0.5
    time_scale: TimeScale = TimeScale.DAY
    # 第 26 节：source → 该(user, domain, time_scale)下的相对可靠度（相对 Null）
    # 未提供的按 1.0 处理，表示「尚未学到任何信息」，不惩罚也不奖励。
    reliability: dict[str, float] = field(default_factory=dict)
    alpha: float = DEFAULT_FUSION_ALPHA


@dataclass
class FusionOutput:
    probability: float
    confidence: float
    contributing_sources: list[str] = field(default_factory=list)
    dependency_groups: dict[str, list[str]] = field(default_factory=dict)
    ignored_signals: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)


def fuse(inp: FusionInput) -> FusionOutput:
    """确定性融合。相同输入永远得到相同输出（可重放、可审计）。"""
    # ---------- 1. 过滤不可用信号 ----------
    usable: list[Signal] = []
    ignored: list[str] = []
    for s in inp.signals:
        if s.degraded:
            # 第 6.1 节：不可用 ≠ 反对。必须跳过，不能当作 0。
            ignored.append(f"{s.source.value}(degraded: {s.degrade_reason})")
            continue
        # 第 57 节：术式在该时间尺度上不支持则跳过
        if s.scale_support() <= 0.0:
            ignored.append(f"{s.source.value}(scale {inp.time_scale.value} unsupported)")
            continue
        usable.append(s)

    if not usable:
        # 没有任何可用信号 → 回落到 Null 基线，并给出低置信度
        return FusionOutput(
            probability=inp.null_probability,
            confidence=0.2,
            ignored_signals=ignored,
            details={"fallback": "no_usable_signal"},
        )

    # ---------- 2. 组内合并（第 20.12 节去相关）----------
    groups: dict[str, list[Signal]] = {}
    for s in usable:
        key = s.dependency_group or f"solo:{s.source.value}"
        groups.setdefault(key, []).append(s)

    group_contribs: list[tuple[float, float, list[str]]] = []  # (贡献值, 权重, 来源)
    dependency_report: dict[str, list[str]] = {}

    for gkey, members in groups.items():
        dependency_report[gkey] = [m.source.value for m in members]

        num = 0.0
        den = 0.0
        for m in members:
            # 权重 = 置信度 × 时间尺度支持度 × 历史可靠度
            rel = inp.reliability.get(m.source.value, 1.0)
            w = m.confidence * m.scale_support() * max(0.0, rel)
            if w <= 0:
                continue
            num += w * m.signed_strength   # direction × strength
            den += w

        if den <= 0:
            ignored.append(f"{gkey}(zero_weight)")
            continue

        # 组内取加权平均，而不是求和 —— 这是去相关的关键
        group_value = num / den
        # 组权重：多源同组不叠加权重，只取组内最大权重（保守）
        group_weight = max(
            (m.confidence * m.scale_support() * inp.reliability.get(m.source.value, 1.0))
            for m in members
        )
        group_contribs.append((group_value, group_weight, [m.source.value for m in members]))

    # ---------- 3. 组间融合 ----------
    total_w = sum(w for _, w, _ in group_contribs)
    if total_w <= MIN_EFFECTIVE_WEIGHT:
        return FusionOutput(
            probability=inp.null_probability,
            confidence=0.25,
            ignored_signals=ignored,
            dependency_groups=dependency_report,
            details={"fallback": "total_weight_too_low"},
        )

    weighted_offset = sum(v * w for v, w, _ in group_contribs) / total_w

    # ---------- 4. 以 Null 为基线做偏移 ----------
    # 禁止 6：弱先验，偏移量受限（alpha）
    raw = inp.null_probability + inp.alpha * weighted_offset
    probability = min(0.99, max(0.01, raw))

    # 置信度：由有效权重总量与信号数决定，且始终受限（第 78 节）
    signal_count = sum(len(srcs) for _, _, srcs in group_contribs)
    confidence = min(0.85, 0.15 + 0.12 * signal_count)

    return FusionOutput(
        probability=round(probability, 4),
        confidence=round(confidence, 3),
        contributing_sources=[s for _, _, srcs in group_contribs for s in srcs],
        dependency_groups=dependency_report,
        ignored_signals=ignored,
        details={
            "null_probability": inp.null_probability,
            "weighted_offset": round(weighted_offset, 4),
            "alpha": inp.alpha,
            "group_count": len(group_contribs),
            "total_weight": round(total_w, 4),
            # 可审计：每个组的贡献（dependency_report 与 group_contribs 同序构造）
            "groups": [
                {
                    "group": gkey,
                    "value": round(v, 4),
                    "weight": round(w, 4),
                    "sources": srcs,
                }
                for gkey, (v, w, srcs) in zip(dependency_report.keys(), group_contribs)
            ],
        },
    )


def fuse_simple(
    signals: list[Signal], null_probability: float = 0.5, time_scale: TimeScale = TimeScale.DAY
) -> FusionOutput:
    """便捷入口：无可靠度矩阵时的融合。"""
    return fuse(
        FusionInput(
            signals=signals,
            null_probability=null_probability,
            time_scale=time_scale,
        )
    )
