"""14 种对抗性攻击（第 20.1 - 20.14 节）。

全部为确定性实现 —— 对抗性审查是系统的最后防线，
它本身不能再依赖一个会产生幻觉的组件。
"""

from .base import Attack, AttackContext, AttackOutcome, Verdict
from .deterministic import ALL_ATTACKS, build_attacks

__all__ = [
    "Attack",
    "AttackContext",
    "AttackOutcome",
    "Verdict",
    "ALL_ATTACKS",
    "build_attacks",
]
