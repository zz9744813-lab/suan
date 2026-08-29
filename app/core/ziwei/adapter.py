"""ZiweiAdapter —— 紫微斗数信号。

对应工程方案：
- 第 6.1 节 紫微斗数
- 第 14 节 统一 Signal Schema
- 第 53 节 Adapter 策略

C-006：紫微斗数作为 Traditional Metaphysical Signal 进入系统，
      其有效性必须由系统自己的长期验证结果决定，不得预先假定有效。

承担：
    本命命盘 / 十二宫 / 主星辅星 / 四化 / 大限 / 流年 / 流月 / 流日

规则：
    程序负责排盘，LLM 不允许自己算命盘。

当前状态：V0.2 未实现。
    available 返回 False → signals() 返回 degraded Signal。
    Fusion 必须跳过 degraded 信号，而不是当作 0
    （当作 0 会让「不可用」被误读为「强烈反对」）。

接入路径见 docs/ENGINES.md。
"""

from __future__ import annotations

from typing import Any

from app.core.base import AdapterQuery, MetaphysicalAdapter, registry
from app.schemas.signal import Signal, SourceType

ENGINE_VERSION = "ziwei-0.1.0"


class ZiweiAdapter(MetaphysicalAdapter):
    source = SourceType.ZIWEI
    engine_name = "iztro"
    engine_version = ENGINE_VERSION

    @property
    def available(self) -> bool:
        # TODO(V0.2): iztro 是 TypeScript 库，Python 侧需封装或经 Node bridge 调用。
        # 接入后改为真实检测。
        return False

    def compute_chart(self, query: AdapterQuery) -> dict[str, Any]:
        """确定性排盘（第 54 节：相同输入必须产生相同输出）。"""
        raise NotImplementedError(
            "紫微斗数 排盘未实现（V0.2）。"
            "参考 SylarLong/iztro，接入步骤见 docs/ENGINES.md。"
        )

    def to_signals(self, query: AdapterQuery, chart: dict[str, Any]) -> list[Signal]:
        """排盘结果 → 统一 Signal（第 14 节）。

        只允许 deterministic 规则映射。
        LLM 解释由对应的 ZiweiAgent 完成，不在此处（第 6.1 节）。
        """
        raise NotImplementedError(
            "紫微斗数 规则映射未实现（V0.2）。"
            "需先在 rules/ 下登记 Rule ID（第 25 节）。"
        )


# 注册到全局 Adapter 注册表（第 53 节）
registry.register(ZiweiAdapter())
