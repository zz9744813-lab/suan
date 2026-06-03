"""Model provider / role routes (spec §16)."""
from __future__ import annotations

import time
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.errors import model_connection_error, not_found
from app.models.model_provider import ModelProvider, ModelRoleAssignment
from app.schemas import (
    APIResponse,
    HealthStatus,
    ModelHealthCheckResult,
    ModelProviderCreate,
    ModelProviderRead,
    ModelProviderTestResult,
    ModelProviderUpdate,
    ModelRoleAssignmentRead,
    ModelRoleAssignmentUpdate,
)
from app.services.llm.client import (
    LLMAuthError,
    LLMConnectionError,
    LLMRateLimitError,
    LLMResponseError,
    LLMRequest,
    LLMMessage,
    get_llm_client,
)


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


# P0-MODEL-3: lightweight per-model health probe.
# Distinct from ``/test`` (which lists every model on the provider) — this
# endpoint sends a 4-token "ping" to *one* specific model and times the
# round-trip. The UI uses the latency to colour-code the role-binding
# matrix and the provider card.

# A ping over 5s but under 15s is still usable, just slow. Over 15s
# we treat it as "unreachable" because most call sites can't wait that
# long either.
_HEALTHY_MAX_MS = 5_000
_DEGRADED_MAX_MS = 15_000


def _classify_health_error(exc: Exception) -> tuple[HealthStatus, str, str | None]:
    """Map an LLM error to a (status, message, suggestion) triple."""
    msg = str(exc) or exc.__class__.__name__
    if isinstance(exc, LLMAuthError):
        return (
            "auth_failed",
            f"鉴权失败：{msg}",
            "检查 API Key 是否有效、是否过期。",
        )
    if isinstance(exc, LLMConnectionError):
        return (
            "unreachable",
            f"无法连接：{msg}",
            "检查 Base URL 是否可访问、网络代理是否畅通。",
        )
    if isinstance(exc, LLMRateLimitError):
        return (
            "degraded",
            f"限流：{msg}",
            "Provider 触发了限流，等几分钟再试或换更小的模型。",
        )
    # LLMResponseError covers 4xx other than 401 (e.g. 404 model not
    # found, 400 invalid request) and malformed JSON responses.
    if isinstance(exc, LLMResponseError):
        lower = msg.lower()
        if "404" in lower or "not found" in lower or "no such model" in lower:
            return (
                "model_missing",
                f"模型不存在：{msg}",
                "模型名拼写错误，或该 Provider 没有这个模型。点击「测试连接」可拉取可用模型列表。",
            )
        return (
            "unknown_error",
            f"Provider 返回错误：{msg}",
            "查看 Provider 详细日志或更换模型后重试。",
        )
    return ("unknown_error", msg, "请稍后重试。")


@router.post("/providers/{provider_id}/health-check", response_model=APIResponse[ModelHealthCheckResult])
async def health_check_provider(
    provider_id: int,
    model: str | None = Query(default=None, description="要探测的模型名；缺省时使用 Provider 的 default_model"),
    db: AsyncSession = Depends(get_db),
) -> APIResponse[ModelHealthCheckResult]:
    """P0-MODEL-3: ping a model with a 4-token call and report status.

    Unlike ``/test`` (which lists every model), this call is intentionally
    tiny: it sends a single ``"ping"`` user message with ``max_tokens=4``
    so even the slowest providers reply in <2s in the happy path. The
    returned ``status`` is a typed enum the UI can render directly as a
    green / yellow / red pill.
    """
    row = await db.get(ModelProvider, provider_id)
    if row is None:
        raise not_found("ModelProvider", provider_id)
    if not row.enabled:
        return {"ok": True, "data": ModelHealthCheckResult(
            ok=False,
            status="unknown_error",
            message="该 Provider 已被禁用，跳过健康检查。",
            suggestion="先在卡片右上角启用该 Provider。",
            model=model or row.default_model or "",
            latency_ms=0,
            checked_at=datetime.utcnow(),
        )}
    target_model = (model or row.default_model or "").strip()
    if not target_model:
        # Fall back to the first known model so the operator can
        # diagnose "I never set a default model" without 400ing.
        if row.model_list:
            target_model = row.model_list[0]
        else:
            return {"ok": True, "data": ModelHealthCheckResult(
                ok=False,
                status="model_missing",
                message="该 Provider 既没有默认模型，也没有任何已知模型。",
                suggestion="先在编辑面板里设置「默认模型」，或点「测试连接」自动拉取模型列表。",
                model="",
                latency_ms=0,
                checked_at=datetime.utcnow(),
            )}
    request = LLMRequest(
        model=target_model,
        messages=[LLMMessage(role="user", content="ping")],
        temperature=0.0,
        max_tokens=4,
    )
    t0 = time.perf_counter()
    try:
        result = await get_llm_client().chat(
            base_url=row.base_url, api_key=row.api_key, request=request,
        )
        latency_ms = int((time.perf_counter() - t0) * 1000)
    except (LLMAuthError, LLMConnectionError, LLMRateLimitError, LLMResponseError) as exc:
        latency_ms = int((time.perf_counter() - t0) * 1000)
        status, message, suggestion = _classify_health_error(exc)
        # Persist on the row so the card and the role matrix can read it
        # back without re-running the probe.
        row.last_health_status = status
        row.last_health_message = message
        row.last_health_latency_ms = latency_ms
        row.last_health_model = target_model
        row.last_health_at = datetime.utcnow()
        await db.flush()
        return {"ok": True, "data": ModelHealthCheckResult(
            ok=False,
            status=status,
            message=message,
            suggestion=suggestion,
            model=target_model,
            latency_ms=latency_ms,
            checked_at=row.last_health_at,
        )}
    # Success path — bucket the latency.
    if latency_ms <= _HEALTHY_MAX_MS:
        status: HealthStatus = "healthy"
        message = f"响应正常（{latency_ms}ms）"
        suggestion = None
    elif latency_ms <= _DEGRADED_MAX_MS:
        status = "degraded"
        message = f"响应偏慢：{latency_ms}ms（> {_HEALTHY_MAX_MS // 1000}s）"
        suggestion = "可继续使用，但建议关注网络质量，或考虑更换更近的 Provider。"
    else:
        # Took too long but eventually replied — we still call it ok
        # because the call did succeed, but flag it as degraded so the
        # operator notices.
        status = "degraded"
        message = f"响应过慢：{latency_ms}ms（> {_DEGRADED_MAX_MS // 1000}s）"
        suggestion = "考虑更换更近的 Provider，或检查网络代理。"
    row.last_health_status = status
    row.last_health_message = message
    row.last_health_latency_ms = latency_ms
    row.last_health_model = target_model
    row.last_health_at = datetime.utcnow()
    await db.flush()
    return {"ok": True, "data": ModelHealthCheckResult(
        ok=True,
        status=status,
        message=message,
        suggestion=suggestion,
        model=target_model,
        latency_ms=latency_ms,
        checked_at=row.last_health_at,
    )}


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
