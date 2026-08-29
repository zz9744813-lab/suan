"""Calendar Core —— 全系统唯一的历法内核（第 6.1 节）。"""

from .core import CalendarCore, CalendarResult, ENGINE_VERSION, get_or_build_snapshot

__all__ = ["CalendarCore", "CalendarResult", "ENGINE_VERSION", "get_or_build_snapshot"]
