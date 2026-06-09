"""项目资料上传、LLM 拆解与记忆写入接口。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, File, Form, UploadFile
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.memory import MemoryCharacter, MemoryForeshadow, MemoryHardFact
from app.models.project_material import ProjectMaterial, ProjectMaterialIngestionRun
from app.schemas.common import ok_response
from app.services.project_material_ingestion import MATERIAL_TYPES, ProjectMaterialIngestionService, count_words_rough, extract_material_text

router = APIRouter(prefix="/projects/{project_id}/materials", tags=["project-materials"])


class ProjectMaterialRead(BaseModel):
    id: int
    project_id: int
    title: str
    filename: str
    material_type: str
    mime_type: str | None = None
    word_count: int
    status: str
    ingest_summary: str = ""
    ingest_result: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(from_attributes=True)


class ProjectMaterialIngestionRunRead(BaseModel):
    id: int
    project_id: int
    material_id: int
    status: str
    summary: str = ""
    result: dict[str, Any] = Field(default_factory=dict)
    created_counts: dict[str, int] = Field(default_factory=dict)
    error_message: str | None = None

    model_config = ConfigDict(from_attributes=True)


@router.get("")
async def list_project_materials(project_id: int, db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(
        select(ProjectMaterial)
        .where(ProjectMaterial.project_id == project_id)
        .order_by(ProjectMaterial.created_at.desc(), ProjectMaterial.id.desc())
    )).scalars().all()
    return ok_response([ProjectMaterialRead.model_validate(row).model_dump() for row in rows])


@router.post("/upload")
async def upload_project_material(
    project_id: int,
    file: UploadFile = File(...),
    material_type: str = Form("other"),
    title: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
):
    material_type = material_type if material_type in MATERIAL_TYPES else "other"
    data = await file.read()
    text = extract_material_text(file.filename or "material.txt", data)
    material = ProjectMaterial(
        project_id=project_id,
        title=title or file.filename or "未命名资料",
        filename=file.filename or "",
        material_type=material_type,
        mime_type=file.content_type,
        extracted_text=text,
        word_count=count_words_rough(text),
        status="uploaded",
    )
    db.add(material)
    await db.commit()
    await db.refresh(material)
    return ok_response(ProjectMaterialRead.model_validate(material).model_dump())


@router.post("/{material_id}/ingest")
async def ingest_project_material(project_id: int, material_id: int, db: AsyncSession = Depends(get_db)):
    material = (await db.execute(
        select(ProjectMaterial).where(ProjectMaterial.project_id == project_id, ProjectMaterial.id == material_id)
    )).scalar_one_or_none()
    if not material:
        return ok_response({"status": "not_found", "message": "资料不存在"})
    service = ProjectMaterialIngestionService(db)
    run = await service.ingest(material)
    await db.commit()
    await db.refresh(run)
    return ok_response(ProjectMaterialIngestionRunRead.model_validate(run).model_dump())


@router.get("/{material_id}/ingestion")
async def get_material_ingestion(project_id: int, material_id: int, db: AsyncSession = Depends(get_db)):
    run = (await db.execute(
        select(ProjectMaterialIngestionRun)
        .where(ProjectMaterialIngestionRun.project_id == project_id, ProjectMaterialIngestionRun.material_id == material_id)
        .order_by(ProjectMaterialIngestionRun.created_at.desc(), ProjectMaterialIngestionRun.id.desc())
        .limit(1)
    )).scalar_one_or_none()
    return ok_response(ProjectMaterialIngestionRunRead.model_validate(run).model_dump() if run else None)


@router.get("/memory/retrieve")
async def retrieve_project_memory(project_id: int, chapter_id: int | None = None, db: AsyncSession = Depends(get_db)):
    characters = (await db.execute(
        select(MemoryCharacter).where(MemoryCharacter.project_id == project_id).order_by(MemoryCharacter.updated_at.desc()).limit(12)
    )).scalars().all()
    facts = (await db.execute(
        select(MemoryHardFact).where(MemoryHardFact.project_id == project_id).order_by(MemoryHardFact.id.desc()).limit(24)
    )).scalars().all()
    foreshadows = (await db.execute(
        select(MemoryForeshadow).where(MemoryForeshadow.project_id == project_id).order_by(MemoryForeshadow.updated_at.desc()).limit(12)
    )).scalars().all()
    payload = {
        "chapter_id": chapter_id,
        "must_follow": [{"id": item.id, "category": item.category, "fact": item.fact} for item in facts],
        "characters": [{"id": item.id, "name": item.name, "role": item.role, "profile": item.base_profile} for item in characters],
        "foreshadowing": [{"id": item.id, "name": item.name, "summary": item.summary, "status": item.status} for item in foreshadows],
        "style": [item.fact for item in facts if item.category in {"style", "style_guide"}],
        "avoid": [item.fact for item in facts if item.category in {"constraint", "forbidden"}],
    }
    return ok_response(payload)
