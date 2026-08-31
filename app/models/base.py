"""SQLModel 基类与共享混入。

对应工程方案第 44 节：Python + FastAPI + Pydantic + SQLModel + SQLite(V1) / PostgreSQL(V2)。
"""

from __future__ import annotations

from datetime import datetime

from app.utils import utcnow

from sqlmodel import SQLModel, Field


class TimestampMixin(SQLModel):
    """全表通用时间戳。C-002 要求预测必须写入完整时间戳。"""

    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
