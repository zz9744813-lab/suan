"""Prompt template center routes."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.errors import not_found
from app.models.prompt import PromptTemplate, PromptVersion
from app.schemas import APIResponse, PromptTemplateRead, PromptVersionRead, PromptVersionUpdate


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
