"""Model provider / role routes (spec §16)."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.errors import model_connection_error, not_found
from app.models.model_provider import ModelProvider, ModelRoleAssignment
from app.schemas import (
    APIResponse,
    ModelProviderCreate,
    ModelProviderRead,
    ModelProviderTestResult,
    ModelProviderUpdate,
    ModelRoleAssignmentRead,
    ModelRoleAssignmentUpdate,
)
from app.services.llm.client import get_llm_client


router = APIRouter(prefix="/models", tags=["models"])


@router.get("/providers", response_model=APIResponse[list[ModelProviderRead]])
async def list_providers(db: AsyncSession = Depends(get_db)) -> APIResponse[list[ModelProviderRead]]:
    rows = (await db.execute(
        select(ModelProvider).order_by(ModelProvider.id.asc())
    )).scalars().all()
    # P0-6: never serialise the raw API key to the client.
    return {"ok": True, "data": [ModelProviderRead.from_orm_masked(r) for r in rows]}


@router.post("/providers", response_model=APIResponse[ModelProviderRead])
async def create_provider(
    body: ModelProviderCreate, db: AsyncSession = Depends(get_db)
) -> APIResponse[ModelProviderRead]:
    row = ModelProvider(
        name=body.name,
        base_url=body.base_url,
        api_key=body.api_key,
        default_model=body.default_model,
        enabled=body.enabled,
        extra=body.extra,
    )
    db.add(row)
    await db.flush()
    return {"ok": True, "data": ModelProviderRead.from_orm_masked(row)}


@router.get("/providers/{provider_id}", response_model=APIResponse[ModelProviderRead])
async def get_provider(provider_id: int, db: AsyncSession = Depends(get_db)) -> APIResponse[ModelProviderRead]:
    row = await db.get(ModelProvider, provider_id)
    if row is None:
        raise not_found("ModelProvider", provider_id)
    return {"ok": True, "data": ModelProviderRead.from_orm_masked(row)}


@router.put("/providers/{provider_id}", response_model=APIResponse[ModelProviderRead])
async def update_provider(
    provider_id: int, body: ModelProviderUpdate, db: AsyncSession = Depends(get_db)
) -> APIResponse[ModelProviderRead]:
    """Update a Provider.

    P0-6 fix: an empty ``api_key`` in the request body means "keep the
    existing key". This lets the UI edit other fields (default_model,
    extra, enabled, ...) without forcing the user to re-paste a long
    secret every time.
    """
    row = await db.get(ModelProvider, provider_id)
    if row is None:
        raise not_found("ModelProvider", provider_id)
    data = body.model_dump()
    new_key = data.pop("api_key", "")
    if new_key:
        row.api_key = new_key
    # else: keep existing api_key untouched
    for k, v in data.items():
        setattr(row, k, v)
    await db.flush()
    return {"ok": True, "data": ModelProviderRead.from_orm_masked(row)}


@router.delete("/providers/{provider_id}", response_model=APIResponse[dict])
async def delete_provider(provider_id: int, db: AsyncSession = Depends(get_db)) -> APIResponse[dict]:
    row = await db.get(ModelProvider, provider_id)
    if row is None:
        raise not_found("ModelProvider", provider_id)
    await db.delete(row)
    return {"ok": True, "data": {"deleted": provider_id}}


@router.post("/providers/{provider_id}/test", response_model=APIResponse[ModelProviderTestResult])
async def test_provider(provider_id: int, db: AsyncSession = Depends(get_db)) -> APIResponse[ModelProviderTestResult]:
    row = await db.get(ModelProvider, provider_id)
    if row is None:
        raise not_found("ModelProvider", provider_id)
    import time
    t0 = time.perf_counter()
    try:
        models = await get_llm_client().list_models(row.base_url, row.api_key)
        row.last_test_status = "ok"
        row.last_test_message = "ok"
        row.last_test_at = datetime.utcnow()
        # persist discovered models
        merged = list(dict.fromkeys((row.model_list or []) + models))
        row.model_list = merged
        if not row.default_model and models:
            row.default_model = models[0]
        await db.flush()
        return {"ok": True, "data": ModelProviderTestResult(
            ok=True,
            message=f"连接成功，识别到 {len(models)} 个模型。",
            models=models,
            latency_ms=int((time.perf_counter() - t0) * 1000),
        )}
    except Exception as exc:
        row.last_test_status = "failed"
        row.last_test_message = str(exc)
        row.last_test_at = datetime.utcnow()
        await db.flush()
        return {"ok": True, "data": ModelProviderTestResult(
            ok=False,
            message=str(exc),
            suggestion=_suggest_for_error(exc),
            latency_ms=int((time.perf_counter() - t0) * 1000),
        )}


def _suggest_for_error(exc: Exception) -> str:
    msg = str(exc)
    if "401" in msg or "Unauthorized" in msg:
        return "API Key 无效，请检查后重试。"
    if "404" in msg:
        return "Base URL 路径不正确，请检查是否需要在末尾追加 /v1 等版本路径。"
    if "无法连接" in msg or "Connection" in msg:
        return "请检查 Base URL 是否可访问，或网络代理是否畅通。"
    return "请稍后重试或更换 Provider。"


# ---------- Role assignments ----------

@router.get("/roles", response_model=APIResponse[list[ModelRoleAssignmentRead]])
async def list_roles(db: AsyncSession = Depends(get_db)) -> APIResponse[list[ModelRoleAssignmentRead]]:
    rows = (await db.execute(
        select(ModelRoleAssignment)
        .options(selectinload(ModelRoleAssignment.provider))
        .order_by(ModelRoleAssignment.role.asc())
    )).scalars().all()
    items: list[ModelRoleAssignmentRead] = []
    for r in rows:
        items.append(ModelRoleAssignmentRead(
            id=r.id, role=r.role,
            provider_id=r.provider_id,
            provider_name=r.provider.name if r.provider else None,
            model=r.model, temperature=r.temperature, max_tokens=r.max_tokens,
            notes=r.notes,
        ))
    return {"ok": True, "data": items}


@router.put("/roles/{role}", response_model=APIResponse[ModelRoleAssignmentRead])
async def set_role(
    role: str, body: ModelRoleAssignmentUpdate, db: AsyncSession = Depends(get_db)
) -> APIResponse[ModelRoleAssignmentRead]:
    row = (await db.execute(
        select(ModelRoleAssignment)
        .options(selectinload(ModelRoleAssignment.provider))
        .where(ModelRoleAssignment.role == role)
    )).scalar_one_or_none()
    if row is None:
        row = ModelRoleAssignment(role=role, **body.model_dump())
        db.add(row)
    else:
        for k, v in body.model_dump().items():
            setattr(row, k, v)
    await db.flush()
    return {"ok": True, "data": ModelRoleAssignmentRead(
        id=row.id, role=row.role,
        provider_id=row.provider_id,
        provider_name=row.provider.name if row.provider else None,
        model=row.model, temperature=row.temperature, max_tokens=row.max_tokens,
        notes=row.notes,
    )}
