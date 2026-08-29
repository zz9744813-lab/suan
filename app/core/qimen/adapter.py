"""QimenAdapter —— 奇门遁甲信号。

对应工程方案：
- 第 6.1 节 奇门遁甲
- 第 14 节 统一 Signal Schema
- 第 53 节 Adapter 策略

C-006：奇门遁甲作为 Traditional Metaphysical Signal 进入系统，
      其有效性必须由系统自己的长期验证结果决定，不得预先假定有效。

承担：
    九宫 / 九星 / 八门 / 八神 / 阴遁阳遁 / 三元 / 节气 / 格局 / 方向 / 时机

V1 优先用于：小时级、日级、具体事件。

当前状态：V0.4 未实现。
    available 返回 False → signals() 返回 degraded Signal。
    Fusion 必须跳过 degraded 信号，而不是当作 0
    （当作 0 会让「不可用」被误读为「强烈反对」）。

接入路径见 docs/ENGINES.md。
"""

from __future__ import annotations

from typing import Any

from app.core.base import AdapterQuery, MetaphysicalAdapter, registry
from app.schemas.signal import Signal, SourceType

ENGINE_VERSION = "qimen-0.1.0"


class QimenAdapter(MetaphysicalAdapter):
    source = SourceType.QIMEN
    engine_name = "qimen-dunjia"
    engine_version = ENGINE_VERSION

    @property
    def available(self) -> bool:
        # TODO(V0.4): 接入 Maximilian-Winter/Qimen-Dunjia 后改为真实检测。
        return False

    def compute_chart(self, query: AdapterQuery) -> dict[str, Any]:
        """确定性排盘（第 54 节：相同输入必须产生相同输出）。"""
        raise NotImplementedError(
            "奇门遁甲 排盘未实现（V0.4）。"
            "参考 Maximilian-Winter/Qimen-Dunjia，接入步骤见 docs/ENGINES.md。"
        )

    def to_signals(self, query: AdapterQuery, chart: dict[str, Any]) -> list[Signal]:
        """排盘结果 → 统一 Signal（第 14 节）。

        只允许 deterministic 规则映射。
        LLM 解释由对应的 QimenAgent 完成，不在此处（第 6.1 节）。
        """
        raise NotImplementedError(
            "奇门遁甲 规则映射未实现（V0.4）。"
            "需先在 rules/ 下登记 Rule ID（第 25 节）。"
        )


# 注册到全局 Adapter 注册表（第 53 节）
registry.register(QimenAdapter())
