"""LiuyaoAdapter —— 六爻信号。

对应工程方案：
- 第 6.1 节 六爻
- 第 14 节 统一 Signal Schema
- 第 53 节 Adapter 策略

C-006：六爻作为 Traditional Metaphysical Signal 进入系统，
      其有效性必须由系统自己的长期验证结果决定，不得预先假定有效。

借鉴：
    纳甲 / 六亲 / 六神 / 世应 / 旺衰 / 空亡 / 暗动 /
    化进化退 / 三合六合 / 墓库 / 黄金卦例测试

架构：程序确定性排盘，LLM 负责断卦。
这是整个工程非常重要的参考架构。

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

ENGINE_VERSION = "liuyao-0.1.0"


class LiuyaoAdapter(MetaphysicalAdapter):
    source = SourceType.LIUYAO
    engine_name = "liuyao-divination"
    engine_version = ENGINE_VERSION

    @property
    def available(self) -> bool:
        # TODO(V0.3): 接入 Johnson-Jia/liuyao-divination 后改为真实检测。
        return False

    def compute_chart(self, query: AdapterQuery) -> dict[str, Any]:
        """确定性排盘（第 54 节：相同输入必须产生相同输出）。"""
        raise NotImplementedError(
            "六爻 排盘未实现（V0.3）。"
            "参考 Johnson-Jia/liuyao-divination，接入步骤见 docs/ENGINES.md。"
        )

    def to_signals(self, query: AdapterQuery, chart: dict[str, Any]) -> list[Signal]:
        """排盘结果 → 统一 Signal（第 14 节）。

        只允许 deterministic 规则映射。
        LLM 解释由对应的 LiuyaoAgent 完成，不在此处（第 6.1 节）。
        """
        raise NotImplementedError(
            "六爻 规则映射未实现（V0.3）。"
            "需先在 rules/ 下登记 Rule ID（第 25 节）。"
        )


# 注册到全局 Adapter 注册表（第 53 节）
registry.register(LiuyaoAdapter())
