"""任务失败后的自动重试与救援。"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.sanitize import sanitize_text
from app.models.model_provider import ModelProvider
from app.models.task import AgentTask, WorkerStatus

NON_RETRYABLE_MARKERS = (
    "cancelled by user",
    "user cancelled",
    "permission denied",
    "unauthorized",
    "invalid api key",
    "project not found",
    "chapter not found",
    "chapter missing",
)

RETRYABLE_MARKERS = (
    "timeout",
    "timed out",
    "connection",
    "rate limit",
    "usage limit",
    "usage limit exceeded",
    "quota",
    "insufficient balance",
    "temporarily",
    "json",
    "utf8",
    "0x00",
    "deadlock",
    "could not serialize",
    "provider",
    "model",
    "llm",
)

SUPPORTED_AUTO_RETRY_TASKS = {
    "chapter_pipeline",
    "project_bootstrap",
    "reader_review",
    "comment_triage",
    "comment_discussion",
    "comment_cleanup",
    "rewrite_from_discussion",
}


def is_retryable_error(error: str | None, *, task_type: str | None = None) -> bool:
    text = (error or "").lower()
    if any(marker in text for marker in NON_RETRYABLE_MARKERS):
        return False
    if any(marker in text for marker in RETRYABLE_MARKERS):
        return True
    return task_type in {"chapter_pipeline", "project_bootstrap", "rewrite_from_discussion"}


def retry_delay_seconds(retry_count: int) -> int:
    return min(30 * (2 ** max(0, retry_count - 1)), 900)


async def quarantine_provider_from_error(db: AsyncSession, error: str) -> bool:
    lower_error = (error or "").lower()
    if not any(marker in lower_error for marker in ("usage limit", "quota", "insufficient balance", "rate limit")):
        return False
    providers = (await db.execute(select(ModelProvider).where(ModelProvider.enabled == True))).scalars().all()  # noqa: E712
    matched = False
    for provider in providers:
        provider_name = (provider.name or "").lower()
        base_url = (provider.base_url or "").lower()
        if (provider_name and provider_name in lower_error) or (base_url and base_url in lower_error):
            provider.last_failure_type = "budget_exhausted"
            provider.last_failure_message = sanitize_text(error)[:2000]
            provider.circuit_state = "open"
            provider.circuit_open_until = datetime.utcnow() + timedelta(hours=24)
            provider.health_score = min(provider.health_score or 0.75, 0.05)
            provider.consecutive_failures = max(int(provider.consecutive_failures or 0), 1)
            matched = True
    return matched


async def apply_task_failure(
    db: AsyncSession,
    task: AgentTask | None,
    error: str,
    *,
    stage: str = "worker",
    retryable: bool | None = None,
    worker_status: WorkerStatus | None = None,
) -> dict[str, Any]:
    if task is None:
        return {"action": "missing", "retryable": False}

    now = datetime.utcnow()
    clean_error = sanitize_text(error or "unknown error")[:4000]
    await quarantine_provider_from_error(db, clean_error)
    can_retry = is_retryable_error(clean_error, task_type=task.task_type) if retryable is None else retryable
    max_retries = max(int(task.max_retries or 8), 8)
    next_retry_count = int(task.retry_count or 0) + 1

    task.error = clean_error
    task.retry_count = next_retry_count
    task.lease_owner = None
    task.lease_expires_at = None
    task.last_heartbeat_at = None

    if can_retry and next_retry_count < max_retries and task.task_type in SUPPORTED_AUTO_RETRY_TASKS:
        delay = retry_delay_seconds(next_retry_count)
        lower_error = clean_error.lower()
        if "usage limit" in lower_error or "quota" in lower_error or "insufficient balance" in lower_error:
            delay = max(delay, 1800)
        payload = dict(task.payload or {})
        payload["auto_retry"] = {
            "stage": stage,
            "retry_count": next_retry_count,
            "max_retries": max_retries,
            "last_error": clean_error[:800],
            "scheduled_at": now.isoformat(),
            "next_retry_at": (now + timedelta(seconds=delay)).isoformat(),
        }
        if next_retry_count >= 2:
            payload["safe_mode"] = True
        task.payload = payload
        task.status = "pending"
        task.started_at = None
        task.finished_at = None
        task.not_before_at = now + timedelta(seconds=delay)
        if worker_status is not None:
            worker_status.current_task_id = None
            worker_status.last_error = clean_error
        return {
            "action": "retry_scheduled",
            "retryable": True,
            "retry_count": next_retry_count,
            "max_retries": max_retries,
            "delay_seconds": delay,
        }

    task.status = "failed"
    task.finished_at = now
    task.not_before_at = None
    if worker_status is not None:
        worker_status.current_task_id = None
        worker_status.last_error = clean_error
        worker_status.consecutive_failures = int(worker_status.consecutive_failures or 0) + 1
    return {
        "action": "failed_final",
        "retryable": can_retry,
        "retry_count": next_retry_count,
        "max_retries": max_retries,
    }


async def rescue_retryable_failed_tasks(
    db: AsyncSession,
    *,
    limit: int = 20,
    reason: str = "auto_rescue",
) -> dict[str, int]:
    now = datetime.utcnow()
    rows = (await db.execute(
        select(AgentTask)
        .where(
            AgentTask.status == "failed",
            AgentTask.task_type.in_(SUPPORTED_AUTO_RETRY_TASKS),
            AgentTask.retry_count < func.greatest(func.coalesce(AgentTask.max_retries, 8), 8),
            or_(AgentTask.not_before_at.is_(None), AgentTask.not_before_at <= now),
        )
        .order_by(AgentTask.updated_at.asc(), AgentTask.id.asc())
        .limit(limit)
    )).scalars().all()
    rescued = 0
    skipped = 0
    for task in rows:
        if not is_retryable_error(task.error, task_type=task.task_type):
            skipped += 1
            continue
        payload = dict(task.payload or {})
        payload["auto_rescue"] = {
            "reason": reason,
            "rescued_at": now.isoformat(),
            "last_error": (task.error or "")[:800],
        }
        if int(task.retry_count or 0) >= 2:
            payload["safe_mode"] = True
        task.payload = payload
        task.status = "pending"
        task.started_at = None
        task.finished_at = None
        task.lease_owner = None
        task.lease_expires_at = None
        task.last_heartbeat_at = None
        task.not_before_at = now
        rescued += 1
    return {"inspected": len(rows), "rescued": rescued, "skipped": skipped}
