"""核心计算层：Calendar Core + 八个术式 Adapter。

第 53 节：每个术式通过 Adapter 接入，输出统一 Schema，
        未来替换算法不会影响 Prediction Engine。

导入本包会触发全部 Adapter 注册到 app.core.base.registry。
因此任何需要列出可用术式的入口（如 /health）都必须先导入本包。
"""

from .base import (
    AdapterQuery,
    AdapterRegistry,
    MetaphysicalAdapter,
    registry,
)

# 触发七个术式 Adapter 注册（import 即注册）
from . import (  # noqa: E402,F401
    bazi,
    face,
    liuyao,
    meihua,
    palm,
    qimen,
    ziwei,
    zhouyi,
)
from .calendar import CalendarCore  # noqa: E402,F401

__all__ = [
    "AdapterQuery",
    "AdapterRegistry",
    "MetaphysicalAdapter",
    "registry",
    "CalendarCore",
]
