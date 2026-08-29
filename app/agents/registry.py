"""Agent 注册表。

对应工程方案第 13 节 Agent 体系（21 个 Agent）。

    FutureScannerAgent      生成待预测目标
    ZiweiAgent              紫微信号解释
    BaziAgent               八字信号解释
    QimenAgent              奇门信号解释
    LiuyaoAgent             六爻解释
    MeihuaAgent             梅花解释
    PalmAgent               掌纹传统映射
    FaceAgent               面相传统映射
    RealityAgent            现实条件分析
    NullAgent               无术数基线
    CandidateAgent          生成可验证预测候选
    FusionAgent             聚合独立信号
    SkepticAgent            反对当前结论
    AdversarialAgent        执行攻击测试
    FreezeAgent             预测预注册
    OutcomeCollectorAgent   收集现实反馈
    OutcomeJudgeAgent       判定结果
    CalibrationAgent        概率校准
    AttributionAgent        错误归因
    LearningAgent           更新可靠度
    ReportAgent             生成日报/周报/月报

第 12 节：所有 Agent 独立运行，提交前互不知晓彼此结论。
"""

from __future__ import annotations

from .base import BaseAgent
from .signal_agents import (
    BaziAgent,
    FaceAgent,
    LiuyaoAgent,
    MeihuaAgent,
    NullAgent,
    PalmAgent,
    QimenAgent,
    RealityAgent,
    ZiweiAgent,
)
from .pipeline_agents import (
    CandidateAgent,
    FreezeAgent,
    FutureScannerAgent,
    SkepticAgent,
)
from .verification_agents import (
    OutcomeCollectorAgent,
    OutcomeJudgeAgent,
    RealityEventExtractor,
)
from .learning_agents import (
    AttributionAgent,
    CalibrationAgent,
    FirstPrinciplesAuditAgent,
    LearningAgent,
    ReportAgent,
)
from .adversarial_agent import AdversarialAgent
from .fusion import fuse, fuse_simple, FusionInput, FusionOutput

# 第 13 节：21 个核心 Agent
AGENT_CLASSES: list[type[BaseAgent]] = [
    FutureScannerAgent,
    ZiweiAgent,
    BaziAgent,
    QimenAgent,
    LiuyaoAgent,
    MeihuaAgent,
    PalmAgent,
    FaceAgent,
    RealityAgent,
    NullAgent,
    CandidateAgent,
    SkepticAgent,
    AdversarialAgent,
    FreezeAgent,
    OutcomeCollectorAgent,
    OutcomeJudgeAgent,
    CalibrationAgent,
    AttributionAgent,
    LearningAgent,
    ReportAgent,
    FirstPrinciplesAuditAgent,
]

# FusionAgent 是确定性融合函数（不调用 LLM），单独导出
FUSION_AGENTS = {"fuse": fuse, "fuse_simple": fuse_simple}

AGENT_NAMES: list[str] = [c.__name__ for c in AGENT_CLASSES] + ["FusionAgent"]


def build(name: str) -> BaseAgent:
    """按名称实例化 Agent。"""
    for cls in AGENT_CLASSES:
        if cls.__name__ == name:
            return cls()
    raise KeyError(f"未知 Agent：{name}。可用：{AGENT_NAMES}")


def all_agents() -> list[BaseAgent]:
    return [c() for c in AGENT_CLASSES]


__all__ = [
    "AGENT_CLASSES",
    "AGENT_NAMES",
    "build",
    "all_agents",
    # 具体 Agent
    "FutureScannerAgent",
    "ZiweiAgent",
    "BaziAgent",
    "QimenAgent",
    "LiuyaoAgent",
    "MeihuaAgent",
    "PalmAgent",
    "FaceAgent",
    "RealityAgent",
    "NullAgent",
    "CandidateAgent",
    "SkepticAgent",
    "AdversarialAgent",
    "FreezeAgent",
    "OutcomeCollectorAgent",
    "OutcomeJudgeAgent",
    "RealityEventExtractor",
    "CalibrationAgent",
    "AttributionAgent",
    "LearningAgent",
    "ReportAgent",
    "FirstPrinciplesAuditAgent",
    # Fusion
    "fuse",
    "fuse_simple",
    "FusionInput",
    "FusionOutput",
    "FUSION_AGENTS",
]
