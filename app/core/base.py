"""术式 Adapter 基类。

对应工程方案第 53 节：

    不要粗暴 fork 后把整个项目揉成一个仓库。
    建立 Adapter：ZiweiAdapter / BaziAdapter / QimenAdapter / LiuyaoAdapter /
                  MeihuaAdapter / PalmAdapter / FaceAdapter
    输出统一 Schema。
    这样未来替换算法不会影响 Prediction Engine。

第 6.1 节硬性规则：
    程序负责排盘，LLM 不允许自己算命盘。

第 14 节硬性规则：
    禁止自然语言报告直接进入 Fusion，必须转换为统一 Signal。
"""

from __future__ import annotations

import hashlib
import json
from abc import ABC, abstractmethod
from datetime import date
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.signal import Domain, Signal, SourceType, TimeScale, TimeWindow


class AdapterQuery(BaseModel):
    """一次术式查询。由 Future Scanner / Prediction 管线构造。"""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    user_id: int
    domain: Domain
    target_event: str = Field(description="Event Ontology，如 career.unexpected_task")
    time_scale: TimeScale = TimeScale.DAY
    window: TimeWindow
    target_date: date
    target_time: str = "00:00"

    # 调用方传入的数据库会话。Adapter 需要读取 BirthProfile。
    # 由调用方注入（便于测试隔离），为 None 时回退到全局 engine。
    session: Any = Field(default=None, exclude=True)

    # 掌纹/面相照片的本地路径（第 64 节：仅本地，不入库、不上传）。
    # 只有 PalmAdapter / FaceAdapter 使用。
    image_path: str | None = Field(default=None, exclude=True)


class MetaphysicalAdapter(ABC):
    """术式 Adapter 抽象基类。

    子类必须实现：
        - compute_chart()：确定性排盘（第 54 节 golden case 可复现）
        - to_signals()：排盘结果 → 统一 Signal

    引擎不可用时：
        返回 degraded=True 的 Signal。Fusion 必须跳过，而不是当作 0。
        （当作 0 会让「不可用」被误读为「强烈反对」）
    """

    source: SourceType
    engine_name: str = "unknown"
    engine_version: str = "unknown"

    # ------------------------------------------------------------------
    @property
    @abstractmethod
    def available(self) -> bool:
        """底层引擎是否可用。"""

    @abstractmethod
    def compute_chart(self, query: AdapterQuery) -> dict[str, Any]:
        """确定性排盘。相同输入必须返回完全相同的结果（第 54 节）。"""

    @abstractmethod
    def to_signals(self, query: AdapterQuery, chart: dict[str, Any]) -> list[Signal]:
        """排盘结果 → 统一 Signal（第 14 节）。

        这里只允许 deterministic 规则映射。
        LLM 解释由对应的 *Agent 完成，不在此处。
        """

    # ------------------------------------------------------------------
    def signals(self, query: AdapterQuery) -> list[Signal]:
        """对外统一入口：排盘 → 信号。引擎不可用时降级。"""
        if not self.available:
            return [self.degraded_signal(query, f"{self.engine_name} 引擎不可用")]

        chart = self.compute_chart(query)
        if not chart:
            return [self.degraded_signal(query, f"{self.engine_name} 排盘返回空")]

        try:
            signals = self.to_signals(query, chart)
        except NotImplementedError as exc:
            return [self.degraded_signal(query, f"{self.engine_name} 规则未实现：{exc}")]

        if not signals:
            # 无信号不等于反对：返回中性信号并标记，交由 Fusion 处理
            return [self.degraded_signal(query, f"{self.engine_name} 未产出信号")]
        return signals

    def degraded_signal(self, query: AdapterQuery, reason: str) -> Signal:
        """降级信号。direction/strength/confidence 全 0 且标记 degraded。

        Fusion 见 degraded=True 必须跳过该信号。
        """
        return Signal(
            source=self.source,
            domain=query.domain,
            target_event=query.target_event,
            direction=0.0,
            strength=0.0,
            confidence=0.0,
            time_window=query.window,
            time_scale=query.time_scale,
            engine_version=self.engine_version,
            degraded=True,
            degrade_reason=reason,
        )

    # ------------------------------------------------------------------
    @staticmethod
    def input_hash(prefix: str, **kwargs: Any) -> str:
        """第 54 节：排盘输入哈希，用于 golden case 与快照缓存。"""
        payload = json.dumps(
            {k: str(v) for k, v in sorted(kwargs.items())},
            sort_keys=True,
            ensure_ascii=False,
        )
        return hashlib.sha256(f"{prefix}:{payload}".encode("utf-8")).hexdigest()

    def _base_signal_kwargs(self, query: AdapterQuery) -> dict[str, Any]:
        return {
            "source": self.source,
            "domain": query.domain,
            "target_event": query.target_event,
            "time_window": query.window,
            "time_scale": query.time_scale,
            "engine_version": self.engine_version,
        }


class AdapterRegistry:
    """术式 Adapter 注册表。便于 Ablation Test（第 33 节）按名摘除。"""

    def __init__(self) -> None:
        self._adapters: dict[SourceType, MetaphysicalAdapter] = {}

    def register(self, adapter: MetaphysicalAdapter) -> None:
        self._adapters[adapter.source] = adapter

    def get(self, source: SourceType) -> Optional[MetaphysicalAdapter]:
        return self._adapters.get(source)

    def all(self) -> list[MetaphysicalAdapter]:
        return list(self._adapters.values())

    def available_sources(self) -> list[SourceType]:
        return [a.source for a in self._adapters.values() if a.available]


registry = AdapterRegistry()
