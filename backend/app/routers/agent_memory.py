"""P10: Agent 分层记忆池 — API Router."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.core.database import session_scope
from app.models.agent_memory import AgentMemoryEntry, MemoryChangeRequest
from app.schemas.agent_memory import (
    AgentMemoryListResponse,
    ChangeRequestCreate,
    ChangeRequestRead,
    ChangeRequestReview,
    ConsolidationJobCreate,
    MemoryArchiveRequest,
    MemoryDemoteRequest,
    MemoryEntryCreate,
    MemoryEntryDetail,
    MemoryEntryListResponse,
    MemoryEntryRead,
    MemoryEntryUpdate,
    MemoryGraphData,
    MemoryMarkConflictRequest,
    MemoryMergeRequest,
    MemoryProjectStats,
    MemoryPromoteRequest,
)
from app.services.agent_memory_service import (
    AgentMemoryService,
    MemoryAuditorService,
    MemoryConsolidatorService,
    MemoryGraphService,
)

router = APIRouter(prefix="/agent-memory", tags=["agent-memory"])


# ============================================================
# Stats & Agents
# ============================================================

@router.get("/projects/{project_id}/stats", response_model=MemoryProjectStats)
async def get_project_stats(project_id: int):
    async with session_scope() as db:
        svc = AgentMemoryService()
        return await svc.get_stats(db, project_id)


@router.get("/projects/{project_id}/agents", response_model=AgentMemoryListResponse)
async def get_project_agents(project_id: int):
    async with session_scope() as db:
        svc = AgentMemoryService()
        return await svc.get_agents(db, project_id)


# ============================================================
# Entries — List / Detail / Create / Update
# ============================================================

@router.get("/projects/{project_id}/entries", response_model=MemoryEntryListResponse)
async def list_entries(
    project_id: int,
    agent_role: str | None = Query(None),
    memory_layer: str | None = Query(None),
    memory_type: str | None = Query(None),
    q: str | None = Query(None),
    tag: str | None = Query(None),
    chapter_id: int | None = Query(None),
    task_id: int | None = Query(None),
    is_conflicted: bool | None = Query(None),
    sort: str = Query("importance"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    async with session_scope() as db:
        svc = AgentMemoryService()
        return await svc.list_memories(
            db, project_id,
            agent_role=agent_role, memory_layer=memory_layer,
            memory_type=memory_type, q=q, tag=tag,
            chapter_id=chapter_id, task_id=task_id,
            is_conflicted=is_conflicted, sort=sort,
            limit=limit, offset=offset,
        )


@router.get("/entries/{memory_id}", response_model=MemoryEntryDetail)
async def get_entry_detail(memory_id: int):
    async with session_scope() as db:
        svc = AgentMemoryService()
        detail = await svc.get_memory_detail(db, memory_id)
        if detail is None:
            raise HTTPException(404, "记忆不存在")
        return detail


@router.post("/projects/{project_id}/entries", response_model=MemoryEntryRead)
async def create_entry(project_id: int, payload: MemoryEntryCreate):
    async with session_scope() as db:
        svc = AgentMemoryService()
        entry = await svc.create_memory(db, project_id, payload)
        # session_scope auto-commits; no explicit commit needed
        return MemoryEntryRead.model_validate(entry)


@router.patch("/entries/{memory_id}", response_model=MemoryEntryRead)
async def update_entry(memory_id: int, payload: MemoryEntryUpdate):
    async with session_scope() as db:
        svc = AgentMemoryService()
        try:
            entry = await svc.update_memory(db, memory_id, payload)
            return MemoryEntryRead.model_validate(entry)
        except ValueError as e:
            raise HTTPException(400, str(e))


# ============================================================
# Actions: Promote / Demote / Archive / Merge / Conflict
# ============================================================

@router.post("/entries/{memory_id}/promote", response_model=MemoryEntryRead)
async def promote_memory(memory_id: int, payload: MemoryPromoteRequest):
    async with session_scope() as db:
        svc = AgentMemoryService()
        try:
            entry = await svc.promote_memory(db, memory_id, payload)
            return MemoryEntryRead.model_validate(entry)
        except ValueError as e:
            raise HTTPException(400, str(e))


@router.post("/entries/{memory_id}/demote", response_model=MemoryEntryRead)
async def demote_memory(memory_id: int, payload: MemoryDemoteRequest):
    async with session_scope() as db:
        svc = AgentMemoryService()
        try:
            entry = await svc.demote_memory(db, memory_id, payload)
            return MemoryEntryRead.model_validate(entry)
        except ValueError as e:
            raise HTTPException(400, str(e))


@router.post("/entries/{memory_id}/archive", response_model=MemoryEntryRead)
async def archive_memory(memory_id: int, payload: MemoryArchiveRequest):
    async with session_scope() as db:
        svc = AgentMemoryService()
        try:
            entry = await svc.archive_memory(db, memory_id, payload)
            return MemoryEntryRead.model_validate(entry)
        except ValueError as e:
            raise HTTPException(400, str(e))


@router.post("/entries/merge", response_model=MemoryEntryRead)
async def merge_memories(payload: MemoryMergeRequest):
    """合并多条记忆为一条. project_id 从第一条 source 记忆获取."""
    async with session_scope() as db:
        # 获取 project_id
        first = await db.get(AgentMemoryEntry, payload.source_ids[0])
        if first is None:
            raise HTTPException(404, f"记忆 {payload.source_ids[0]} 不存在")
        project_id = first.project_id

        svc = AgentMemoryService()
        try:
            entry = await svc.merge_memories(db, project_id, payload)
            return MemoryEntryRead.model_validate(entry)
        except ValueError as e:
            raise HTTPException(400, str(e))


@router.post("/entries/{memory_id}/mark-conflict")
async def mark_conflict(memory_id: int, payload: MemoryMarkConflictRequest):
    async with session_scope() as db:
        svc = AgentMemoryService()
        try:
            link = await svc.mark_conflict(db, memory_id, payload)
            return {"ok": True, "link_id": link.id}
        except ValueError as e:
            raise HTTPException(400, str(e))


# ============================================================
# Consolidation
# ============================================================

@router.post("/projects/{project_id}/consolidate")
async def consolidate_project(project_id: int, payload: ConsolidationJobCreate):
    async with session_scope() as db:
        svc = MemoryConsolidatorService()
        results = await svc.run_consolidation(db, project_id, payload.job_types)
        return {"ok": True, "results": results}


# ============================================================
# Graph
# ============================================================

@router.get("/projects/{project_id}/graph", response_model=MemoryGraphData)
async def get_project_graph(
    project_id: int,
    agent_role: str | None = Query(None),
):
    async with session_scope() as db:
        svc = MemoryGraphService()
        return await svc.get_project_graph(db, project_id, agent_role)


# ============================================================
# Change Requests (永久记忆修改)
# ============================================================

change_router = APIRouter(prefix="/agent-memory/change-requests", tags=["agent-memory"])


@change_router.post("/", response_model=ChangeRequestRead)
async def create_change_request(payload: ChangeRequestCreate):
    async with session_scope() as db:
        entry = await db.get(AgentMemoryEntry, payload.memory_id)
        if entry is None:
            raise HTTPException(404, "记忆不存在")
        svc = MemoryAuditorService()
        try:
            cr = await svc.create_change_request(db, entry.project_id, payload)
            return ChangeRequestRead.model_validate(cr)
        except ValueError as e:
            raise HTTPException(400, str(e))


@change_router.get("/{request_id}", response_model=ChangeRequestRead)
async def get_change_request(request_id: int):
    async with session_scope() as db:
        cr = await db.get(MemoryChangeRequest, request_id)
        if cr is None:
            raise HTTPException(404, "ChangeRequest 不存在")
        return ChangeRequestRead.model_validate(cr)


@change_router.post("/{request_id}/review", response_model=ChangeRequestRead)
async def review_change_request(request_id: int, payload: ChangeRequestReview):
    async with session_scope() as db:
        svc = MemoryAuditorService()
        try:
            if payload.status == "approved":
                cr = await svc.approve_change_request(
                    db, request_id, reviewer="user", note=payload.review_note,
                )
            else:
                cr = await svc.reject_change_request(
                    db, request_id, reviewer="user", note=payload.review_note,
                )
            return ChangeRequestRead.model_validate(cr)
        except ValueError as e:
            raise HTTPException(400, str(e))
