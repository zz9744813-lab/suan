"""通用工具：时间源等。

datetime 模块的旧 utcnow() 自 Python 3.12 起弃用（3.13 会告警）。数据库列均为
naive datetime，因此这里返回 naive UTC（now(timezone.utc) 去除 tzinfo），语义
与旧接口完全一致，但不再触发弃用警告。
"""

from __future__ import annotations

from datetime import datetime, timezone


def utcnow() -> datetime:
    """naive UTC 当前时间（等价旧的 datetime.utcnow()）。"""
    return datetime.now(timezone.utc).replace(tzinfo=None)
