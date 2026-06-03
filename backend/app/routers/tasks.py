"""Task creation / inspection routes."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.errors import not_found
from app.models.project import Chapter
from app.models.task import AgentEvent, AgentStep, AgentTask
from app.schemas import (
    APIResponse,
    AgentEventRead,
    AgentStepRead,
    AgentTaskCreate,
    AgentTaskRead,
)


router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.get("", response_model=APIResponse[list[AgentTaskRead]])
async def list_tasks(
    project_id: int | None = None,
    chapter_id: int | None = None,
    status: str | None = None,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[list[AgentTaskRead]]:
    stmt = select(AgentTask).order_by(AgentTask.id.desc()).limit(min(limit, 200))
    if project_id is not None:
        stmt = stmt.where(AgentTask.project_id == project_id)
    if chapter_id is not None:
        stmt = stmt.where(AgentTask.chapter_id == chapter_id)
    if status is not None:
        stmt = stmt.where(AgentTask.status == status)
    rows = (await db.execute(stmt)).scalars().all()
    return {"ok": True, "data": [AgentTaskRead.model_validate(r) for r in rows]}


@router.post("", response_model=APIResponse[AgentTaskRead])
async def create_task(
    body: AgentTaskCreate, db: AsyncSession = Depends(get_db)
) -> APIResponse[AgentTaskRead]:
    if body.chapter_id is not None:
        ch = await db.get(Chapter, body.chapter_id)
        if ch is None:
            raise not_found("Chapter", body.chapter_id)
    row = AgentTask(
        project_id=body.project_id,
        chapter_id=body.chapter_id,
        task_type=body.task_type,
        priority=body.priority,
        payload=body.payload,
        max_retries=body.max_retries,
    )
    db.add(row)
    await db.flush()
    return {"ok": True, "data": AgentTaskRead.model_validate(row)}


@router.get("/{task_id}", response_model=APIResponse[AgentTaskRead])
async def get_task(task_id: int, db: AsyncSession = Depends(get_db)) -> APIResponse[AgentTaskRead]:
    row = await db.get(AgentTask, task_id)
    if row is None:
        raise not_found("AgentTask", task_id)
    return {"ok": True, "data": AgentTaskRead.model_validate(row)}


@router.get("/{task_id}/steps", response_model=APIResponse[list[AgentStepRead]])
async def task_steps(task_id: int, db: AsyncSession = Depends(get_db)) -> APIResponse[list[AgentStepRead]]:
    rows = (await db.execute(
        select(AgentStep).where(AgentStep.task_id == task_id).order_by(AgentStep.id.asc())
    )).scalars().all()
    return {"ok": True, "data": [AgentStepRead.model_validate(r) for r in rows]}


@router.get("/{task_id}/events", response_model=APIResponse[list[AgentEventRead]])
async def task_events(task_id: int, db: AsyncSession = Depends(get_db)) -> APIResponse[list[AgentEventRead]]:
    rows = (await db.execute(
        select(AgentEvent).where(AgentEvent.task_id == task_id).order_by(AgentEvent.id.asc())
    )).scalars().all()
    return {"ok": True, "data": [AgentEventRead.model_validate(r) for r in rows]}


@router.post("/{task_id}/cancel", response_model=APIResponse[AgentTaskRead])
async def cancel_task(task_id: int, db: AsyncSession = Depends(get_db)) -> APIResponse[AgentTaskRead]:
    row = await db.get(AgentTask, task_id)
    if row is None:
        raise not_found("AgentTask", task_id)
    row.status = "cancelled"
    await db.flush()
    return {"ok": True, "data": AgentTaskRead.model_validate(row)}


@router.post("/{task_id}/retry", response_model=APIResponse[AgentTaskRead])
async def retry_task(task_id: int, db: AsyncSession = Depends(get_db)) -> APIResponse[AgentTaskRead]:
    row = await db.get(AgentTask, task_id)
    if row is None:
        raise not_found("AgentTask", task_id)
    row.status = "pending"
    row.retry_count += 1
    row.error = None
    await db.flush()
    return {"ok": True, "data": AgentTaskRead.model_validate(row)}
