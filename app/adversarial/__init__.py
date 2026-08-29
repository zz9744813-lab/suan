"""对抗性审查系统（第 20 / 21 节）。这是核心基础设施，不是附属 Agent。"""

from .gate import AdversarialGate, GateResult, run_gate

__all__ = ["AdversarialGate", "GateResult", "run_gate"]
