"""P4: /api/agent-roles/* — 角色绑定矩阵 + 角色 CRUD + 模型绑定 + 运行历史.

按 spec 05_P4 §9:
  GET    /api/agent-roles                       角色列表
  GET    /api/agent-roles/matrix                角色绑定矩阵 (核心端点)
  POST   /api/agent-roles                       新增 Agent
  GET    /api/agent-roles/{id}                  角色详情
  PUT    /api/agent-roles/{id}                  更新角色
  DELETE /api/agent-roles/{id}                  删除/归档角色
  PUT    /api/agent-roles/{id}/model-binding    改绑模型
  PUT    /api/agent-roles/{id}/prompt-binding   改绑 prompt
  GET    /api/agent-runs/current                所有角色当前状态 (matrix 用)
  GET    /api/agent-runs?agent_role_id=&limit=  运行历史
  GET    /api/agent-runs/{id}                   单次 run
  GET    /api/agent-runs/{id}/events            run 事件流

设计要点:
  - 角色状态 (status) 派生自最新一条 AgentRun + 是否有 in-progress
    AgentStep. P4 §15 禁 6 禁止"没有运行记录的 Agent 假装运行":
    从不主动 push "running", 只读真实数据.
  - 默认 11 个角色在 seed() 里建 (P4 §10). 已有则跳过.
  - AgentRun 行 P4 这一轮不会自动产生 (worker 没接进来), 矩阵
    状态会显示 "待命" + 0 run. P4.1 (worker 集成) 会从 AgentStep
    派生 AgentRun.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.errors import not_found
from app.models.agent_role import (
    AgentModelBinding,
    AgentPromptBinding,
    AgentRole,
    AgentRun,
    AgentRunEvent,
)
from app.models.model_provider import ModelProvider
from app.models.task import AgentStep
from app.schemas.agent_role import (
    AgentModelBindingRead,
    AgentModelBindingUpdate,
    AgentPromptBindingRead,
    AgentPromptBindingUpdate,
    AgentRoleCreate,
    AgentRoleMatrixItem,
    AgentRoleMatrixResponse,
    AgentRoleRead,
    AgentRoleUpdate,
    AgentRunEventRead,
    AgentRunRead,
)

router = APIRouter(prefix="/agent-roles", tags=["agent-roles"])

# 跟 router 放一起, 路径是 /api/agent-runs, mount 时再加 prefix
agent_runs_router = APIRouter(prefix="/agent-runs", tags=["agent-runs"])


# ============================================================
# 角色矩阵 (核心) — 一次返回所有角色 + 绑定 + 最新 run
# ============================================================
@router.get("/matrix", response_model=AgentRoleMatrixResponse)
async def get_agent_role_matrix(
    db: AsyncSession = Depends(get_db),
) -> AgentRoleMatrixResponse:
    """P4 §4 / §9.4 — 角色绑定矩阵.

    对每个 enabled AgentRole:
      - 找最新一条 AgentRun (按 created_at desc)
      - 算 status (P4 §4 状态枚举)
      - 拉最近 10 条 run + 最近 50 条 event

    没 run 历史的角色 → status=待命 (P4 §15 禁 6).
    """
    roles = (await db.execute(
        select(AgentRole).order_by(
            AgentRole.visible_in_matrix.desc(),
            AgentRole.category.asc(),
            AgentRole.id.asc(),
        )
    )).scalars().all()

    # 一次拉所有 binding / provider, 避免 N+1
    bindings = (await db.execute(
        select(AgentModelBinding)
    )).scalars().all()
    binding_by_role: dict[int, AgentModelBinding] = {b.agent_role_id: b for b in bindings}

    prompt_bindings = (await db.execute(
        select(AgentPromptBinding)
    )).scalars().all()
    pb_by_role: dict[int, AgentPromptBinding] = {pb.agent_role_id: pb for pb in prompt_bindings}

    providers = (await db.execute(select(ModelProvider))).scalars().all()
    provider_by_id: dict[int, ModelProvider] = {p.id: p for p in providers}

    # 一次拉所有 run (按 role 聚合时再分组), 限制每 role 10 条 + 50 事件
    all_runs = (await db.execute(
        select(AgentRun).order_by(AgentRun.created_at.desc()).limit(500)
    )).scalars().all()
    runs_by_role: dict[int, list[AgentRun]] = {}
    for r in all_runs:
        runs_by_role.setdefault(r.agent_role_id, []).append(r)

    all_run_ids = [r.id for r in all_runs[:200]]
    events_by_run: dict[int, list[AgentRunEvent]] = {}
    if all_run_ids:
        ev_rows = (await db.execute(
            select(AgentRunEvent)
            .where(AgentRunEvent.agent_run_id.in_(all_run_ids))
            .order_by(AgentRunEvent.created_at.desc())
            .limit(2000)
        )).scalars().all()
        for ev in ev_rows:
            events_by_run.setdefault(ev.agent_run_id, []).append(ev)

    items: list[AgentRoleMatrixItem] = []
    section_counts: dict[str, int] = {}
    for role in roles:
        section_counts[role.category] = section_counts.get(role.category, 0) + 1
        binding = binding_by_role.get(role.id)
        pb = pb_by_role.get(role.id)
        provider_name = None
        if binding and binding.provider_id:
            p = provider_by_id.get(binding.provider_id)
            if p:
                provider_name = p.name
        role_runs = runs_by_role.get(role.id, [])
        latest = role_runs[0] if role_runs else None
        # status 派生: latest 是 succeeded/failed → 直接用; 是
        # running/waiting → 如果有 in-progress AgentStep 仍在
        # 跑 (started_at not null, finished_at is null) 算 "运行中",
        # 否则算 "完成/失败"; 没 run 就算 "待命"
        if latest is None:
            status = "disabled" if not role.enabled else "idle"
        else:
            status = latest.status
            if status in ("running", "waiting"):
                # 看最近 in-progress AgentStep 是不是真的还在
                # (P4 这一轮 AgentRun 是离线的, 靠 AgentStep 校验)
                in_progress = (await db.execute(
                    select(func.count(AgentStep.id))
                    .where(
                        AgentStep.agent_name == role.key,
                        AgentStep.started_at.is_not(None),
                        AgentStep.finished_at.is_(None),
                    )
                )).scalar_one() or 0
                if in_progress == 0:
                    # 没有真正在跑的 step, 视为待命 (P4 §15 禁 6)
                    status = "idle"
        items.append(AgentRoleMatrixItem(
            role=AgentRoleRead.model_validate(role),
            binding=AgentModelBindingRead.model_validate(binding) if binding else None,
            prompt_binding=AgentPromptBindingRead.model_validate(pb) if pb else None,
            status=status,
            status_label=_STATUS_LABEL.get(status, status),
            current_task=latest.current_task if latest else None,
            progress=latest.progress if latest else 0.0,
            provider_name=provider_name,
            model_name=(binding.model_name if binding else None) or (latest.model_name if latest else None),
            last_run_id=latest.id if latest else None,
            last_run_at=latest.created_at if latest else None,
            last_error=latest.error_message if latest else None,
            total_runs=len(role_runs),
            recent_runs=[AgentRunRead.model_validate(r) for r in role_runs[:10]],
            recent_events=[AgentRunEventRead.model_validate(e)
                           for r in role_runs[:3]
                           for e in events_by_run.get(r.id, [])[:20]],
        ))

    return AgentRoleMatrixResponse(items=items, section_counts=section_counts)


_STATUS_LABEL: dict[str, str] = {
    "idle":      "待命",
    "queued":    "排队",
    "running":   "运行中",
    "waiting":   "等待上游",
    "succeeded": "完成",
    "failed":    "失败",
    "disabled":  "禁用",
}


# ============================================================
# AgentRole CRUD
# ============================================================
@router.get("", response_model=list[AgentRoleRead])
async def list_agent_roles(
    category: str | None = Query(default=None),
    enabled_only: bool = Query(default=False),
    db: AsyncSession = Depends(get_db),
) -> list[AgentRoleRead]:
    stmt = select(AgentRole)
    if category:
        stmt = stmt.where(AgentRole.category == category)
    if enabled_only:
        stmt = stmt.where(AgentRole.enabled == True)  # noqa: E712
    stmt = stmt.order_by(AgentRole.category.asc(), AgentRole.id.asc())
    rows = (await db.execute(stmt)).scalars().all()
    return [AgentRoleRead.model_validate(r) for r in rows]


@router.post("", response_model=AgentRoleRead)
async def create_agent_role(
    body: AgentRoleCreate, db: AsyncSession = Depends(get_db),
) -> AgentRoleRead:
    # key 唯一
    exists = (await db.execute(
        select(AgentRole).where(AgentRole.key == body.key)
    )).scalar_one_or_none()
    if exists is not None:
        raise HTTPException(409, f"AgentRole key={body.key!r} 已存在")
    row = AgentRole(**body.model_dump())
    db.add(row)
    await db.flush()
    await db.refresh(row)
    return AgentRoleRead.model_validate(row)


@router.get("/{role_id}", response_model=AgentRoleRead)
async def get_agent_role(
    role_id: int, db: AsyncSession = Depends(get_db),
) -> AgentRoleRead:
    row = await db.get(AgentRole, role_id)
    if row is None:
        raise not_found("AgentRole", role_id)
    return AgentRoleRead.model_validate(row)


@router.put("/{role_id}", response_model=AgentRoleRead)
async def update_agent_role(
    role_id: int, body: AgentRoleUpdate, db: AsyncSession = Depends(get_db),
) -> AgentRoleRead:
    row = await db.get(AgentRole, role_id)
    if row is None:
        raise not_found("AgentRole", role_id)
    data = body.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(row, k, v)
    row.updated_at = datetime.utcnow()
    await db.flush()
    return AgentRoleRead.model_validate(row)


@router.delete("/{role_id}")
async def delete_agent_role(
    role_id: int, db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """P4 §7.4 (9) "可删除或归档". 默认硬删, 关联 binding/run 都
    CASCADE. 未来可以加 archive=true 的软删参数."""
    row = await db.get(AgentRole, role_id)
    if row is None:
        raise not_found("AgentRole", role_id)
    await db.delete(row)
    await db.flush()
    return {"deleted": role_id}


# ============================================================
# 模型绑定 (P4 §9.3 PUT /api/agent-roles/{id}/model-binding)
# ============================================================
@router.put("/{role_id}/model-binding", response_model=AgentModelBindingRead)
async def put_agent_model_binding(
    role_id: int, body: AgentModelBindingUpdate, db: AsyncSession = Depends(get_db),
) -> AgentModelBindingRead:
    role = await db.get(AgentRole, role_id)
    if role is None:
        raise not_found("AgentRole", role_id)
    existing = (await db.execute(
        select(AgentModelBinding).where(AgentModelBinding.agent_role_id == role_id)
    )).scalar_one_or_none()
    data = body.model_dump(exclude_unset=True)
    if existing is None:
        existing = AgentModelBinding(agent_role_id=role_id, **data)
        db.add(existing)
    else:
        for k, v in data.items():
            setattr(existing, k, v)
        existing.updated_at = datetime.utcnow()
    await db.flush()
    return AgentModelBindingRead.model_validate(existing)


@router.put("/{role_id}/prompt-binding", response_model=AgentPromptBindingRead)
async def put_agent_prompt_binding(
    role_id: int, body: AgentPromptBindingUpdate, db: AsyncSession = Depends(get_db),
) -> AgentPromptBindingRead:
    role = await db.get(AgentRole, role_id)
    if role is None:
        raise not_found("AgentRole", role_id)
    existing = (await db.execute(
        select(AgentPromptBinding).where(AgentPromptBinding.agent_role_id == role_id)
    )).scalar_one_or_none()
    data = body.model_dump(exclude_unset=True)
    if existing is None:
        existing = AgentPromptBinding(agent_role_id=role_id, **data)
        db.add(existing)
    else:
        for k, v in data.items():
            setattr(existing, k, v)
        existing.updated_at = datetime.utcnow()
    await db.flush()
    return AgentPromptBindingRead.model_validate(existing)


# ============================================================
# Agent Run 端点 (P4 §9.4)
# ============================================================
@agent_runs_router.get("/current", response_model=list[AgentRunRead])
async def list_current_agent_runs(
    db: AsyncSession = Depends(get_db),
) -> list[AgentRunRead]:
    """所有角色"当前"run (按 created_at desc limit 1 per role).

    P4 这一轮 AgentRun 不自动产生, 所以多半是空. matrix 端点
    才是真正给前端用的 (有 status 派生).
    """
    # 简单返回最近 50 条
    rows = (await db.execute(
        select(AgentRun).order_by(AgentRun.created_at.desc()).limit(50)
    )).scalars().all()
    return [AgentRunRead.model_validate(r) for r in rows]


@agent_runs_router.get("", response_model=list[AgentRunRead])
async def list_agent_runs(
    agent_role_id: int | None = Query(default=None),
    project_id: int | None = Query(default=None),
    limit: int = Query(default=50, le=500),
    db: AsyncSession = Depends(get_db),
) -> list[AgentRunRead]:
    stmt = select(AgentRun)
    if agent_role_id:
        stmt = stmt.where(AgentRun.agent_role_id == agent_role_id)
    if project_id:
        stmt = stmt.where(AgentRun.project_id == project_id)
    stmt = stmt.order_by(AgentRun.created_at.desc()).limit(limit)
    rows = (await db.execute(stmt)).scalars().all()
    return [AgentRunRead.model_validate(r) for r in rows]


@agent_runs_router.get("/{run_id}", response_model=AgentRunRead)
async def get_agent_run(
    run_id: int, db: AsyncSession = Depends(get_db),
) -> AgentRunRead:
    row = await db.get(AgentRun, run_id)
    if row is None:
        raise not_found("AgentRun", run_id)
    return AgentRunRead.model_validate(row)


@agent_runs_router.get("/{run_id}/events", response_model=list[AgentRunEventRead])
async def get_agent_run_events(
    run_id: int, limit: int = Query(default=100, le=500),
    db: AsyncSession = Depends(get_db),
) -> list[AgentRunEventRead]:
    rows = (await db.execute(
        select(AgentRunEvent)
        .where(AgentRunEvent.agent_run_id == run_id)
        .order_by(AgentRunEvent.created_at.desc())
        .limit(limit)
    )).scalars().all()
    return [AgentRunEventRead.model_validate(r) for r in rows]
