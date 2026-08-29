"""数据模型汇总。

对应工程方案第 36 节：全部 30+ 张表。

导入顺序即建表顺序（外键依赖：users 必须先建）。
"""

from .base import TimestampMixin
from .core import BirthProfile, CalendarSnapshot, User
from .metaphysical import (
    BaziChart,
    FaceFeature,
    LiuyaoChart,
    MeihuaChart,
    PalmFeature,
    QimenChart,
    ZiweiChart,
)
from .reality import DailyState, RealityEvent, UserPlan
from .prediction import (
    ForecastCandidate,
    PredictionFreeze,
    PredictionRecord,
    PredictionVersion,
    SignalRecord,
)
from .scoring import (
    CalibrationBin,
    OutcomeEvidence,
    OutcomeRecord,
    OutcomeRequestRecord,
    PredictionScore,
)
from .registry import (
    AgentOutput,
    AgentRun,
    ModelVersion,
    PromptVersion,
    Rule,
    RuleMetric,
    RuleVersion,
)
from .adversarial import AdversarialFinding, AdversarialTest
from .learning import (
    AblationResult,
    ExperimentRun,
    LearningHypothesis,
    ModelPromotion,
    ShadowExperiment,
)

__all__ = [
    # base
    "TimestampMixin",
    # core
    "User",
    "BirthProfile",
    "CalendarSnapshot",
    # metaphysical
    "ZiweiChart",
    "BaziChart",
    "QimenChart",
    "LiuyaoChart",
    "MeihuaChart",
    "PalmFeature",
    "FaceFeature",
    # reality
    "RealityEvent",
    "DailyState",
    "UserPlan",
    # prediction
    "ForecastCandidate",
    "SignalRecord",
    "PredictionRecord",
    "PredictionVersion",
    "PredictionFreeze",
    # scoring
    "OutcomeRequestRecord",
    "OutcomeRecord",
    "OutcomeEvidence",
    "PredictionScore",
    "CalibrationBin",
    # registry
    "Rule",
    "RuleVersion",
    "RuleMetric",
    "AgentRun",
    "AgentOutput",
    "PromptVersion",
    "ModelVersion",
    # adversarial
    "AdversarialTest",
    "AdversarialFinding",
    # learning
    "LearningHypothesis",
    "ShadowExperiment",
    "ModelPromotion",
    "AblationResult",
    "ExperimentRun",
]
