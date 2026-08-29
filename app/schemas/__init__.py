"""传输模型（Pydantic）。

    signal.py      第 14 节 统一 Signal Schema
    prediction.py  第 15 / 16 节 Prediction Schema 与冻结
    outcome.py     第 17 / 18 节 Outcome 与三方 Judge
"""

from .signal import (
    DEFAULT_SCALE_SUPPORT,
    Domain,
    Evidence,
    EvidenceSource,
    Signal,
    SourceType,
    TimeScale,
    TimeWindow,
)
from .prediction import (
    InformationValue,
    OutcomeScale,
    Prediction,
    PredictionCandidate,
    PredictionStatus,
    VisibilityMode,
)
from .outcome import (
    JudgeRole,
    JudgeVerdict,
    Outcome,
    OutcomeRequest,
    RealityEvent,
)

__all__ = [
    # signal
    "Signal",
    "Evidence",
    "EvidenceSource",
    "SourceType",
    "Domain",
    "TimeScale",
    "TimeWindow",
    "DEFAULT_SCALE_SUPPORT",
    # prediction
    "Prediction",
    "PredictionCandidate",
    "PredictionStatus",
    "VisibilityMode",
    "InformationValue",
    "OutcomeScale",
    # outcome
    "Outcome",
    "OutcomeRequest",
    "JudgeVerdict",
    "JudgeRole",
    "RealityEvent",
]
