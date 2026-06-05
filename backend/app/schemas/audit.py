"""S5-T2 审计日志 — Pydantic schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


# ============================================================
# AuditLog — 审计日志
# ============================================================

class AuditLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int | None
    chapter_id: int | None
    agent_task_id: int | None
    event_type: str
    actor_type: str
    actor_key: str | None
    action: str
    details: dict | None
    created_at: datetime


class AuditLogListResponse(BaseModel):
    items: list[AuditLogRead]
    total: int


# ============================================================
# 写入请求 (供内部 service 调用, 前端只读)
# ============================================================

class AuditLogCreate(BaseModel):
    """内部 service 写入审计日志 (不暴露为独立 POST 端点)."""

    project_id: int | None = None
    chapter_id: int | None = None
    agent_task_id: int | None = None
    event_type: str = Field(..., min_length=1, max_length=60)
    actor_type: str = Field(default="system", min_length=1, max_length=20)
    actor_key: str | None = Field(default=None, max_length=80)
    action: str = Field(..., min_length=1, max_length=255)
    details: dict | None = None
