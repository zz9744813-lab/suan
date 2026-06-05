"""S5-T2 审计日志 — Service 层.

提供 audit_log() 方法, 供各 service/router 在关键操作后调用。
"""

from __future__ import annotations

from logging import Logger, getLogger
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog

_logger: Logger = getLogger(__name__)


async def audit_log(
    db: AsyncSession,
    *,
    event_type: str,
    action: str,
    actor_type: str = "system",
    actor_key: str | None = None,
    project_id: int | None = None,
    chapter_id: int | None = None,
    agent_task_id: int | None = None,
    details: dict[str, Any] | None = None,
) -> AuditLog | None:
    """写入一条审计日志.

    Usage::

        from app.services.audit_service import audit_log

        await audit_log(
            db,
            event_type="model_switch",
            action="planner 模型切换 → gpt-4o (provider=1)",
            actor_type="user",
            actor_key="admin",
            project_id=1,
            details={"agent_key": "planner", "new_model": "gpt-4o", "provider_id": 1},
        )
    """
    try:
        entry = AuditLog(
            project_id=project_id,
            chapter_id=chapter_id,
            agent_task_id=agent_task_id,
            event_type=event_type,
            actor_type=actor_type,
            actor_key=actor_key,
            action=action[:255],
            details=details,
        )
        db.add(entry)
        # 不用 await db.commit() — 由调用方在 session_scope 内统一 commit
        await db.flush()
        return entry
    except Exception as exc:
        _logger.warning("audit_log 写入失败: %s", exc)
        return None


# ── 便捷函数 ────────────────────────────────────────────────────

def _make_details(**kw: Any) -> dict[str, Any]:
    """构造 details dict, 过滤 None 值."""
    return {k: v for k, v in kw.items() if v is not None}


async def log_model_switch(
    db: AsyncSession,
    *,
    actor_type: str,
    actor_key: str | None,
    project_id: int | None,
    agent_key: str,
    old_provider_id: int | None,
    old_model: str | None,
    new_provider_id: int,
    new_model: str,
) -> None:
    await audit_log(
        db,
        event_type="model_switch",
        action=f"{agent_key} 模型切换 → {new_model}",
        actor_type=actor_type,
        actor_key=actor_key,
        project_id=project_id,
        details=_make_details(
            agent_key=agent_key,
            old_provider_id=old_provider_id,
            old_model=old_model,
            new_provider_id=new_provider_id,
            new_model=new_model,
        ),
    )


async def log_prompt_binding_change(
    db: AsyncSession,
    *,
    actor_type: str,
    actor_key: str | None,
    project_id: int,
    agent_key: str,
    genre: str,
    old_template_id: int | None,
    new_template_id: int,
    source: str,
) -> None:
    await audit_log(
        db,
        event_type="prompt_binding_change",
        action=f"{agent_key}[{genre}] prompt 绑定 → template_id={new_template_id} ({source})",
        actor_type=actor_type,
        actor_key=actor_key,
        project_id=project_id,
        details=_make_details(
            agent_key=agent_key,
            genre=genre,
            old_template_id=old_template_id,
            new_template_id=new_template_id,
            source=source,
        ),
    )


async def log_review_action(
    db: AsyncSession,
    *,
    actor_type: str,
    actor_key: str | None,
    project_id: int,
    chapter_id: int | None,
    comment_id: int,
    action: str,
    decision: str | None = None,
) -> None:
    await audit_log(
        db,
        event_type="review_action",
        action=f"评论#{comment_id} {action}",
        actor_type=actor_type,
        actor_key=actor_key,
        project_id=project_id,
        chapter_id=chapter_id,
        details=_make_details(comment_id=comment_id, decision=decision),
    )


async def log_agent_task(
    db: AsyncSession,
    *,
    event_type: str,
    project_id: int | None,
    agent_task_id: int,
    agent_key: str,
    error: str | None = None,
) -> None:
    await audit_log(
        db,
        event_type=event_type,
        action=f"AgentTask#{agent_task_id} {event_type}",
        actor_type="worker",
        actor_key=agent_key,
        project_id=project_id,
        agent_task_id=agent_task_id,
        details=_make_details(error=error[:500] if error else None),
    )


async def log_settings_change(
    db: AsyncSession,
    *,
    actor_type: str,
    actor_key: str | None,
    project_id: int,
    changed_fields: list[str],
    old_values: dict,
    new_values: dict,
) -> None:
    await audit_log(
        db,
        event_type="settings_change",
        action=f"项目#{project_id} 设置变更: {', '.join(changed_fields)}",
        actor_type=actor_type,
        actor_key=actor_key,
        project_id=project_id,
        details={"changed_fields": changed_fields, "old": old_values, "new": new_values},
    )
