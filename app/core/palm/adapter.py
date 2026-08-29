"""PalmAdapter —— 掌纹系统信号。

对应工程方案：
- 第 8 节 掌纹系统
- 第 14 节 统一 Signal Schema
- 第 53 节 Adapter 策略

C-006：掌纹系统作为 Traditional Metaphysical Signal 进入系统，
      其有效性必须由系统自己的长期验证结果决定，不得预先假定有效。

流程：
    原图 → MediaPipe 手部关键点 → 透视/角度校正 → 掌纹检测 →
    掌纹分类 → 长度/曲率/断点/深度特征 → 结构化 PalmFeatures →
    Traditional Palm Rule Engine → PalmSignal

而不是：照片 → Vision LLM → 直接算命。

隐私（第 64 节）：原始照片本地保存，上传 LLM 前必须裁剪，可关闭云 Vision。

当前状态：V0.8 未实现。
    available 返回 False → signals() 返回 degraded Signal。
    Fusion 必须跳过 degraded 信号，而不是当作 0
    （当作 0 会让「不可用」被误读为「强烈反对」）。

接入路径见 docs/ENGINES.md。
"""

from __future__ import annotations

from typing import Any

from app.core.base import AdapterQuery, MetaphysicalAdapter, registry
from app.schemas.signal import Signal, SourceType

ENGINE_VERSION = "palm-0.1.0"


class PalmAdapter(MetaphysicalAdapter):
    source = SourceType.PALM
    engine_name = "palmistry"
    engine_version = ENGINE_VERSION

    @property
    def available(self) -> bool:
        # TODO(V0.8): 需要 MediaPipe + OpenCV 手部关键点与掌纹检测。
        # 另受 ENABLE_CLOUD_VISION 开关控制（第 64 节）。
        from app.config import get_settings

        if not get_settings().ENABLE_CLOUD_VISION:
            return False
        return False

    def compute_chart(self, query: AdapterQuery) -> dict[str, Any]:
        """确定性排盘（第 54 节：相同输入必须产生相同输出）。"""
        raise NotImplementedError(
            "掌纹系统 排盘未实现（V0.8）。"
            "参考 yeonsumia/palmistry + MediaPipe，接入步骤见 docs/ENGINES.md。"
        )

    def to_signals(self, query: AdapterQuery, chart: dict[str, Any]) -> list[Signal]:
        """排盘结果 → 统一 Signal（第 14 节）。

        只允许 deterministic 规则映射。
        LLM 解释由对应的 PalmAgent 完成，不在此处（第 6.1 节）。
        """
        raise NotImplementedError(
            "掌纹系统 规则映射未实现（V0.8）。"
            "需先在 rules/ 下登记 Rule ID（第 25 节）。"
        )


# 注册到全局 Adapter 注册表（第 53 节）
registry.register(PalmAdapter())
