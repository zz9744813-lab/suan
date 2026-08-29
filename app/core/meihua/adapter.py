"""MeihuaAdapter —— 梅花易数信号。

对应工程方案：
- 第 6.1 节 梅花易数
- 第 14 节 统一 Signal Schema
- 第 53 节 Adapter 策略

C-006：梅花易数作为 Traditional Metaphysical Signal 进入系统，
      其有效性必须由系统自己的长期验证结果决定，不得预先假定有效。

承担：
    时间起卦 / 数字起卦 / 本卦 / 互卦 / 变卦 / 体用 / 五行

当前状态：V0.3 未实现。
    available 返回 False → signals() 返回 degraded Signal。
    Fusion 必须跳过 degraded 信号，而不是当作 0
    （当作 0 会让「不可用」被误读为「强烈反对」）。

接入路径见 docs/ENGINES.md。
"""

from __future__ import annotations

from typing import Any

from app.core.base import AdapterQuery, MetaphysicalAdapter, registry
from app.schemas.signal import Signal, SourceType

ENGINE_VERSION = "meihua-0.1.0"


class MeihuaAdapter(MetaphysicalAdapter):
    source = SourceType.MEIHUA
    engine_name = "meihua-yi"
    engine_version = ENGINE_VERSION

    @property
    def available(self) -> bool:
        # TODO(V0.3): 接入 handsomejustin/meihua-yi 后改为真实检测。
        return False

    def compute_chart(self, query: AdapterQuery) -> dict[str, Any]:
        """确定性排盘（第 54 节：相同输入必须产生相同输出）。"""
        raise NotImplementedError(
            "梅花易数 排盘未实现（V0.3）。"
            "参考 handsomejustin/meihua-yi，接入步骤见 docs/ENGINES.md。"
        )

    def to_signals(self, query: AdapterQuery, chart: dict[str, Any]) -> list[Signal]:
        """排盘结果 → 统一 Signal（第 14 节）。

        只允许 deterministic 规则映射。
        LLM 解释由对应的 MeihuaAgent 完成，不在此处（第 6.1 节）。
        """
        raise NotImplementedError(
            "梅花易数 规则映射未实现（V0.3）。"
            "需先在 rules/ 下登记 Rule ID（第 25 节）。"
        )


# 注册到全局 Adapter 注册表（第 53 节）
registry.register(MeihuaAdapter())
