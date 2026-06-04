"""Prompt template center routes."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.errors import bad_request, conflict, not_found
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
