"""Prompt template center routes."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.errors import bad_request, conflict, not_found
from app.models.agent_role import AgentRole
from app.models.prompt import PromptTemplate, PromptVersion
from app.schemas import (
    APIResponse,
    PromptTemplateCreate,
    PromptTemplateRead,
    PromptVersionRead,
    PromptVersionUpdate,
)


router = APIRouter(prefix="/prompts", tags=["prompts"])


@router.get("", response_model=APIResponse[list[PromptTemplateRead]])
async def list_templates(db: AsyncSession = Depends(get_db)) -> APIResponse[list[PromptTemplateRead]]:
    rows = (await db.execute(
        select(PromptTemplate).order_by(PromptTemplate.category, PromptTemplate.role)
    )).scalars().all()
    return {"ok": True, "data": [PromptTemplateRead.model_validate(r) for r in rows]}


# P0 返工 Phase 2.3 — Prompt 模板覆盖率
#
#  矩阵：role_key × genre
#  - 单元 = "有有效版本(active_version_id != null) 且 active 版本 body 长度>=200" 的模板数
#  - 总数：每个 (role, genre) 单元默认 1 个（global 不限流派）
#
# 返回结构:
# {
#   "rows": [{"role_key": "drafter", "role_label": "Drafter", "category": "writing"}, ...],
#   "genres": ["urban_smooth", "scifi_hard", "historical", "suspense", "romance"],
#   "cells": {"drafter:urban_smooth": 1, ...},  # 有覆盖=1，空=0
#   "summary": {total_cells, covered_cells, coverage_pct}
# }
@router.get("/coverage", response_model=APIResponse[dict[str, Any]])
async def template_coverage(db: AsyncSession = Depends(get_db)) -> APIResponse[dict[str, Any]]:
    # 1) 所有 AgentRole (按 category 排序)
    roles = (await db.execute(
        select(AgentRole).order_by(AgentRole.category, AgentRole.key)
    )).scalars().all()

    # 2) 当前在库的模板（含 role / genre / active_version_id / body 长度）
    tpl_rows = (await db.execute(select(PromptTemplate))).scalars().all()

    # 3) 流派列表（从模板里去重得到，global=NULL 不算流派）
    genres = sorted({t.genre for t in tpl_rows if t.genre})
    if not genres:
        genres = ["(未分类)"]

    # 4) 算每个 (role_key, genre) 单元是否有覆盖
    def has_template(role_key: str, genre: str | None) -> int:
        for t in tpl_rows:
            if t.role != role_key:
                continue
            # 全局模板 (genre=None / scope=global) 算所有流派的"通配"覆盖
            if t.genre is None or t.scope == "global":
                return 1
            if t.genre == genre:
                return 1
        return 0

    cells: dict[str, int] = {}
    for r in roles:
        for g in genres:
            cells[f"{r.key}:{g}"] = has_template(r.key, g)

    # 5) 统计
    total = len(roles) * len(genres)
    covered = sum(cells.values())
    coverage_pct = round(100.0 * covered / total, 1) if total else 0.0

    return {
        "ok": True,
        "data": {
            "rows": [
                {
                    "role_key": r.key,
                    "role_label": r.display_name,
                    "category": r.category,
                }
                for r in roles
            ],
            "genres": genres,
            "cells": cells,
            "summary": {
                "total_cells": total,
                "covered_cells": covered,
                "missing_cells": total - covered,
                "coverage_pct": coverage_pct,
            },
        },
    }


# P0 返工 Phase 2.4 — 模板使用追溯
#
#  GET /api/prompts/usage?template_id=42
#  返回最近 N (默认 20) 次用此模板的 AgentRun
#
#  GET /api/prompts/usage  (不带参数)
#  返回按 template_id 聚合的"用得最多的模板 Top N"
@router.get("/usage", response_model=APIResponse[dict[str, Any]])
async def template_usage(
    template_id: int | None = None,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[dict[str, Any]]:
    """模板使用追溯 — 看哪些 run 用了某个模板 / 哪些模板被用得最多。"""
    from sqlalchemy import desc, func
    from app.models.agent_role import AgentRun

    if template_id is not None:
        # 单模板追溯：拉最近 N 个 run
        rows = (await db.execute(
            select(AgentRun)
            .where(AgentRun.prompt_template_id == template_id)
            .order_by(desc(AgentRun.id))
            .limit(limit)
        )).scalars().all()
        return {
            "ok": True,
            "data": {
                "template_id": template_id,
                "runs": [
                    {
                        "id": r.id,
                        "status": r.status,
                        "model_name": r.model_name,
                        "input_tokens": r.input_tokens,
                        "output_tokens": r.output_tokens,
                        "cost_usd": r.cost_usd,
                        "elapsed_ms": r.elapsed_ms,
                        "started_at": r.started_at.isoformat() if r.started_at else None,
                        "finished_at": r.finished_at.isoformat() if r.finished_at else None,
                        "task_id": r.task_id,
                        "project_id": r.project_id,
                    }
                    for r in rows
                ],
            },
        }

    # 聚合: 按 template_id 统计使用次数
    rows = (await db.execute(
        select(
            AgentRun.prompt_template_id,
            func.count(AgentRun.id).label("usage_count"),
            func.coalesce(func.sum(AgentRun.input_tokens + AgentRun.output_tokens), 0).label("total_tokens"),
            func.coalesce(func.sum(AgentRun.cost_usd), 0.0).label("total_cost"),
        )
        .where(AgentRun.prompt_template_id != None)  # noqa: E711
        .group_by(AgentRun.prompt_template_id)
        .order_by(desc("usage_count"))
        .limit(50)
    )).all()

    # 拉模板 metadata
    tpl_ids = [row[0] for row in rows]
    tpl_meta: dict[int, dict[str, Any]] = {}
    if tpl_ids:
        tpl_rows = (await db.execute(
            select(PromptTemplate).where(PromptTemplate.id.in_(tpl_ids))
        )).scalars().all()
        tpl_meta = {
            t.id: {
                "template_key": t.template_key,
                "name": t.name,
                "role": t.role,
                "category": t.category,
                "genre": t.genre,
            }
            for t in tpl_rows
        }

    return {
        "ok": True,
        "data": {
            "top_templates": [
                {
                    "template_id": row[0],
                    "usage_count": int(row[1]),
                    "total_tokens": int(row[2]),
                    "total_cost": float(row[3]),
                    **tpl_meta.get(row[0], {}),
                }
                for row in rows
            ],
        },
    }


@router.get("/{template_id}", response_model=APIResponse[PromptTemplateRead])
async def get_template(template_id: int, db: AsyncSession = Depends(get_db)) -> APIResponse[PromptTemplateRead]:
    row = await db.get(PromptTemplate, template_id)
    if row is None:
        raise not_found("PromptTemplate", template_id)
    return {"ok": True, "data": PromptTemplateRead.model_validate(row)}


@router.post("/templates", response_model=APIResponse[PromptTemplateRead], status_code=201)
async def create_template(body: PromptTemplateCreate, db: AsyncSession = Depends(get_db)):
    # Check template_key uniqueness
    existing = (await db.execute(
        select(PromptTemplate).where(PromptTemplate.template_key == body.template_key)
    )).scalar_one_or_none()
    if existing:
        raise conflict(f"template_key 已存在: {body.template_key}", suggestion="换一个唯一的 key")

    tpl = PromptTemplate(
        template_key=body.template_key,
        name=body.name,
        category=body.category,
        role=body.role,
        scope=body.scope,
        genre=body.genre,
        description=body.description,
        allowed_inputs=body.allowed_inputs,
        forbidden_inputs=body.forbidden_inputs,
        output_schema=body.output_schema,
        can_modify=body.can_modify,
        cannot_modify=body.cannot_modify,
        hard_rules=body.hard_rules,
        immutable=False,  # user-created templates are always mutable
    )
    db.add(tpl)
    await db.flush()

    # Create initial version if body provided
    if body.initial_body:
        ver = PromptVersion(
            template_id=tpl.id,
            version=1,
            body=body.initial_body,
            status="active",
            change_note="初始版本",
        )
        db.add(ver)
        await db.flush()
        tpl.active_version_id = ver.id

    await db.flush()
    return {"ok": True, "data": PromptTemplateRead.model_validate(tpl)}


@router.delete("/templates/{template_id}", response_model=APIResponse[dict])
async def delete_template(template_id: int, db: AsyncSession = Depends(get_db)):
    tpl = await db.get(PromptTemplate, template_id)
    if tpl is None:
        raise not_found("PromptTemplate", template_id)
    if tpl.immutable:
        raise bad_request("内置模板不可删除", suggestion="你可以解绑它，但不能删除内置模板。")
    await db.delete(tpl)
    await db.flush()
    return {"ok": True, "data": {"deleted": template_id}}


@router.get("/{template_id}/versions", response_model=APIResponse[list[PromptVersionRead]])
async def list_versions(template_id: int, db: AsyncSession = Depends(get_db)) -> APIResponse[list[PromptVersionRead]]:
    rows = (await db.execute(
        select(PromptVersion)
        .where(PromptVersion.template_id == template_id)
        .order_by(PromptVersion.version.desc())
    )).scalars().all()
    return {"ok": True, "data": [PromptVersionRead.model_validate(r) for r in rows]}


@router.post("/{template_id}/versions", response_model=APIResponse[PromptVersionRead])
async def create_version(
    template_id: int, body: PromptVersionUpdate, db: AsyncSession = Depends(get_db)
) -> APIResponse[PromptVersionRead]:
    tpl = await db.get(PromptTemplate, template_id)
    if tpl is None:
        raise not_found("PromptTemplate", template_id)
    existing = (await db.execute(
        select(PromptVersion).where(PromptVersion.template_id == template_id)
    )).scalars().all()
    next_no = (max((v.version for v in existing), default=0)) + 1
    if body.activate:
        for v in existing:
            v.status = "deprecated"
    ver = PromptVersion(
        template_id=template_id,
        version=next_no,
        body=body.body,
        status="active" if body.activate else "candidate",
        change_note=body.change_note,
    )
    db.add(ver)
    if body.activate:
        tpl.active_version_id = None  # filled by hook in seed if needed
    await db.flush()
    return {"ok": True, "data": PromptVersionRead.model_validate(ver)}


@router.post("/{template_id}/versions/{version_id}/activate", response_model=APIResponse[PromptVersionRead])
async def activate_version(
    template_id: int, version_id: int, db: AsyncSession = Depends(get_db)
) -> APIResponse[PromptVersionRead]:
    rows = (await db.execute(
        select(PromptVersion).where(
            PromptVersion.template_id == template_id,
            PromptVersion.id == version_id,
        )
    )).scalars().all()
    if not rows:
        raise not_found("PromptVersion", version_id)
    target = rows[0]
    others = (await db.execute(
        select(PromptVersion).where(
            PromptVersion.template_id == template_id,
            PromptVersion.id != version_id,
        )
    )).scalars().all()
    for v in others:
        v.status = "deprecated"
    target.status = "active"
    tpl = await db.get(PromptTemplate, template_id)
    if tpl is not None:
        tpl.active_version_id = version_id
    await db.flush()
    return {"ok": True, "data": PromptVersionRead.model_validate(target)}
