"""Model provider / role routes (spec §16)."""
from __future__ import annotations

import asyncio
import json
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
    ModelHealthCheckItem,
    ModelHealthCheckResult,
    ModelProviderCreate,
    ModelProviderRead,
    ModelProviderTestResult,
    ModelProviderUpdate,
    ModelRoleAssignmentRead,
    ModelRoleAssignmentUpdate,
    ProviderPreviewModelsRequest,
    ProviderPreviewModelsResponse,
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
from app.services.model_call_recorder import ModelCallRecorder
from app.services.model_selector import is_text_role_model_compatible


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
        if v is not None:
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


# P0-MODEL-7: stateless model-list preview. The user is in the middle
# of creating or editing a Provider and wants to pick ``default_model``
# from a dropdown instead of typing it by hand. The /test endpoint
# can't help here because it requires a saved provider_id. This
# endpoint calls ``LLMClient.list_models`` directly with the form's
# base_url + api_key and returns the result without touching the DB.
@router.post(
    "/providers/preview-models",
    response_model=APIResponse[ProviderPreviewModelsResponse],
)
async def preview_provider_models(
    body: ProviderPreviewModelsRequest,
) -> APIResponse[ProviderPreviewModelsResponse]:
    t0 = time.perf_counter()
    try:
        models = await get_llm_client().list_models(body.base_url, body.api_key)
        latency_ms = int((time.perf_counter() - t0) * 1000)
        return {
            "ok": True,
            "data": ProviderPreviewModelsResponse(
                ok=True,
                models=models,
                message=f"成功拉取到 {len(models)} 个模型。",
                suggestion=None,
                latency_ms=latency_ms,
            ),
        }
    except Exception as exc:
        latency_ms = int((time.perf_counter() - t0) * 1000)
        return {
            "ok": True,
            "data": ProviderPreviewModelsResponse(
                ok=False,
                models=[],
                message=str(exc),
                suggestion=_suggest_for_error(exc),
                latency_ms=latency_ms,
            ),
        }


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

# P15 / P0-HEALTH-1: per-test latency budgets. The probe runs four
# tests and each one has its own SLA. ``json_output`` and
# ``critic_schema`` get a slightly larger budget than the simple ping
# because the model is doing more work.
# P0-MODEL-11: tighten the long_text budget. With reasoning
# models now skipping the planning preamble (auto-injected
# ``reasoning_effort="low"``), a 1000-char Chinese paragraph
# arrives in 5-10s on a fast provider. 20s is plenty; if a model
# needs more, the probe reports a warning ("warning", not "failed")
# so the operator can still see slow-but-working behaviour without
# burning 30+10=40s of the operator's wall clock.
_HEALTHY_MS_PER_TEST = {
    "short_chat": 5_000,
    "json_output": 8_000,
    "critic_schema": 10_000,
    "long_text": 25_000,
}

# Role → which tests must pass for the role to be considered safe.
# A model that fails critic_schema is NOT safe for the ``Critic``
# role even if the other tests pass. A model that fails long_text
# isn't safe for ``Draft`` / ``Rewrite`` because those roles output
# 2000-6000-token chapters.
_ROLE_REQUIREMENTS: dict[str, dict[str, Any]] = {
    # core
    "Chief":        {"need": ["short_chat", "json_output"], "nice": ["long_text"]},
    "Planner":      {"need": ["short_chat", "json_output"], "nice": ["long_text"]},
    # writing
    "Draft":        {"need": ["short_chat", "long_text"],   "nice": ["json_output"]},
    "Critic":       {"need": ["short_chat", "json_output", "critic_schema"], "nice": []},
    "Rewrite":      {"need": ["short_chat", "long_text"],   "nice": ["json_output"]},
    "Continuity":   {"need": ["short_chat", "json_output"], "nice": ["long_text"]},
    # memory
    "MemoryUpdate": {"need": ["short_chat", "json_output"], "nice": ["long_text"]},
    "Learning":     {"need": ["short_chat", "json_output"], "nice": []},
}




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
    """P0-MODEL-3 + P15 / P0-HEALTH-1: per-model health probe.

    Runs FOUR tests in sequence and reports each one independently:

    1. ``short_chat``    — single 1-token ping; reply must arrive in < 5s.
    2. ``json_output``   — model must return STRICT JSON (no markdown
       fences, no leading prose). Required for Planner / Critic / Memory.
    3. ``critic_schema`` — model must follow the Critic JSON schema
       (``total`` / ``dimension_scores`` / ``issues`` / ``rewrite_required``).
       This is the test that catches "model goes off the rails on
       structured output" failures.
    4. ``long_text``     — model must output ≥ 1000 chars of Chinese
       prose. Required for Draft / Rewrite (2K-6K output tokens).

    The top-level ``status`` is derived from the items:
      - all four pass  → ``healthy``
      - some pass      → ``degraded``
      - any auth / network failure  → ``auth_failed`` / ``unreachable``

    The role-binding matrix uses ``recommended_roles`` to warn the
    operator when a critical-role (Critic, Draft, ...) model failed
    the test that role needs.
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
            results=[],
            score=0,
            recommended_roles={},
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
                results=[],
                score=0,
                recommended_roles={},
            )}

    if not is_text_role_model_compatible("health_check", target_model):
        checked_at = datetime.utcnow()
        message = "已跳过：该模型看起来是生图、视频、音频或视觉专用模型，不执行文本 Agent 健康探针。"
        row.last_health_status = "unknown_error"
        row.last_health_message = message
        row.last_health_latency_ms = 0
        row.last_health_model = target_model
        row.last_health_at = checked_at
        row.last_health_full = {
            "results": [
                _skipped_item("short_chat", message).model_dump(),
                _skipped_item("json_output", message).model_dump(),
                _skipped_item("critic_schema", message).model_dump(),
                _skipped_item("long_text", message).model_dump(),
            ],
            "score": 0,
            "recommended_roles": {},
            "checked_at": checked_at.isoformat(),
            "skipped_reason": "media_model",
        }
        await db.flush()
        return {"ok": True, "data": ModelHealthCheckResult(
            ok=False,
            status="unknown_error",
            message=message,
            suggestion="给文本 Agent 绑定 chat/completions 文本模型；生图、视频、音频模型不要放进自动分配池。",
            model=target_model,
            latency_ms=0,
            checked_at=checked_at,
            results=[ModelHealthCheckItem(**r) for r in row.last_health_full["results"]],
            score=0,
            recommended_roles={},
        )}

    client = get_llm_client()
    checked_at = datetime.utcnow()

    # Run all four tests. The first FAIL (auth / unreachable) bails
    # the rest because subsequent tests will just repeat the same
    # error. We still record the failure on the items we DIDN'T get
    # to so the UI shows "skipped" for the unrun ones.
    results: list[ModelHealthCheckItem] = []
    fatal: tuple[HealthStatus, str, str | None] | None = None

    # ---- 1. short_chat ----
    item = await _probe_short_chat(client, row, target_model, db)
    results.append(item)
    if item.status == "failed":
        fatal = _fatal_from_message(item.message)

    # ---- 2. json_output ----
    if fatal is None:
        item = await _probe_json_output(client, row, target_model, db)
        results.append(item)
    else:
        results.append(_skipped_item("json_output", fatal[1]))

    # ---- 3. critic_schema ----
    if fatal is None:
        item = await _probe_critic_schema(client, row, target_model, db)
        results.append(item)
    else:
        results.append(_skipped_item("critic_schema", fatal[1]))

    # ---- 4. long_text ----
    if fatal is None:
        item = await _probe_long_text(client, row, target_model, db)
        results.append(item)
    else:
        results.append(_skipped_item("long_text", fatal[1]))

    # ---- aggregate ----
    overall_status, overall_message, overall_suggestion, total_latency_ms, score = _aggregate_health(results, fatal)
    recommended_roles = _derive_recommended_roles(results)

    # Persist on the row so the card and the role matrix can read it
    # back without re-running the probe.
    row.last_health_status = overall_status
    row.last_health_message = overall_message
    row.last_health_latency_ms = total_latency_ms
    row.last_health_model = target_model
    row.last_health_at = checked_at
    # P15 / P0-HEALTH-1: per-test detail + role recommendations. Single
    # JSON blob so the role matrix can colour-code risky bindings
    # without us re-running the probe on every page load.
    row.last_health_full = {
        "results": [it.model_dump() for it in results],
        "score": score,
        "recommended_roles": recommended_roles,
        "checked_at": checked_at.isoformat(),
    }
    await db.flush()

    return {"ok": True, "data": ModelHealthCheckResult(
        ok=overall_status in ("healthy", "degraded"),
        status=overall_status,
        message=overall_message,
        suggestion=overall_suggestion,
        model=target_model,
        latency_ms=total_latency_ms,
        checked_at=checked_at,
        results=results,
        score=score,
        recommended_roles=recommended_roles,
    )}


# ---------------------------------------------------------------------------
# Health probe helpers (P15 / P0-HEALTH-1)
# ---------------------------------------------------------------------------

def _fatal_from_message(msg: str) -> tuple[HealthStatus, str, str | None]:
    """Map a per-test failure message to a (status, message, suggestion)."""
    if "鉴权失败" in msg or "401" in msg or "Unauthorized" in msg:
        return ("auth_failed", msg, "检查 API Key 是否有效、是否过期。")
    if "无法连接" in msg or "Connection" in msg or "Timeout" in msg:
        return ("unreachable", msg, "检查 Base URL 是否可访问、网络代理是否畅通。")
    if "模型不存在" in msg or "404" in msg or "no such model" in msg.lower():
        return ("model_missing", msg, "模型名拼写错误，或该 Provider 没有这个模型。")
    return ("unknown_error", msg, "请稍后重试或更换 Provider。")


def _skipped_item(name: str, reason: str) -> ModelHealthCheckItem:
    return ModelHealthCheckItem(
        name=name,  # type: ignore[arg-type]
        status="skipped",
        latency_ms=0,
        message=f"前置测试失败，已跳过：{reason}",
        suggestion=None,
        raw_preview=None,
    )


async def _run_probe(
    client,
    row: ModelProvider,
    target_model: str,
    *,
    db: AsyncSession | None = None,
    probe_name: str,
    messages: list[LLMMessage],
    max_tokens: int,
    response_format: dict[str, str] | None = None,
    probe_timeout: float = 30.0,
) -> tuple[int, str, str | None]:
    """Send a single probe call and return (latency_ms, raw_content, error_or_None).

    ``probe_timeout`` caps the *total* time spent in this probe, *including*
    any retries the underlying ``client.chat`` performs. Without it, a stuck
    connection would inherit the chat client's 600s read timeout and a
    2-attempt retry could make a single 「健康检查」 request last > 20
    minutes — which is what was making the UI look like a black screen.
    """
    request = LLMRequest(
        model=target_model,
        messages=messages,
        temperature=0.0,
        max_tokens=max_tokens,
        response_format=response_format,
    )
    t0 = time.perf_counter()
    event = None
    if db is not None:
        recorder = ModelCallRecorder()
        event = await recorder.record_selection(
            db,
            provider_id=row.id,
            model_name=target_model,
            agent_role_key=f"health_check:{probe_name}",
            selection_mode="health_check",
            provider_name=row.name,
            event_type="model_health_check",
            event_category="health",
            summary=f"健康测试 {probe_name}: {row.name}/{target_model}",
        )
    try:
        coro = client.chat(
            base_url=row.base_url, api_key=row.api_key, request=request,
        )
        result = await asyncio.wait_for(coro, timeout=probe_timeout)
        latency_ms = int((time.perf_counter() - t0) * 1000)
        if db is not None and event is not None:
            recorder = ModelCallRecorder()
            await recorder.record_success(
                db,
                event,
                latency_ms=latency_ms,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                cost_usd=result.cost_usd,
            )
            event.event_type = "model_health_check"
            event.event_category = "health"
            event.summary = f"健康测试 {probe_name} 通过: {row.name}/{target_model} · {latency_ms}ms"
        return latency_ms, result.content, None
    except asyncio.TimeoutError:
        latency_ms = int((time.perf_counter() - t0) * 1000)
        if db is not None and event is not None:
            recorder = ModelCallRecorder()
            await recorder.record_failure(
                db,
                event,
                "timeout",
                f"健康测试 {probe_name} 超过 {probe_timeout:.0f}s 未返回",
            )
            event.event_type = "model_health_check"
            event.event_category = "health"
        return (
            latency_ms,
            "",
            f"timeout: 探针超过 {probe_timeout:.0f}s 未返回，请检查网络或更换 Provider。",
        )
    except (LLMAuthError, LLMConnectionError, LLMRateLimitError, LLMResponseError) as exc:
        latency_ms = int((time.perf_counter() - t0) * 1000)
        status, msg, sug = _classify_health_error(exc)
        if db is not None and event is not None:
            recorder = ModelCallRecorder()
            await recorder.record_failure(
                db,
                event,
                _health_status_to_failure_type(status),
                msg,
            )
            event.event_type = "model_health_check"
            event.event_category = "health"
        # squash the long trace; the caller will format a short error
        return latency_ms, "", f"{status}: {msg} | {sug or ''}".strip(" |")


def _health_status_to_failure_type(status: HealthStatus) -> str:
    if status == "auth_failed":
        return "auth_error"
    if status == "unreachable":
        return "connection_error"
    if status == "model_missing":
        return "model_not_found"
    if status == "degraded":
        return "rate_limited"
    return "unknown"


async def _probe_short_chat(client, row, target_model, db: AsyncSession) -> ModelHealthCheckItem:
    messages = [LLMMessage(role="user", content="ping")]
    latency_ms, content, err = await _run_probe(
        client, row, target_model, db=db, probe_name="short_chat", messages=messages, max_tokens=4,
        probe_timeout=_HEALTHY_MS_PER_TEST["short_chat"] / 1000 + 5,
    )
    if err:
        return ModelHealthCheckItem(
            name="short_chat",
            status="failed",
            latency_ms=latency_ms,
            message=err.split("|", 1)[0].strip(),
            suggestion="请检查网络、API Key 和 Base URL。",
            raw_preview=None,
        )
    budget = _HEALTHY_MS_PER_TEST["short_chat"]
    if latency_ms > budget:
        return ModelHealthCheckItem(
            name="short_chat",
            status="warning",
            latency_ms=latency_ms,
            message=f"响应偏慢：{latency_ms}ms（> {budget // 1000}s）",
            suggestion="可继续使用，但建议关注网络质量。",
            raw_preview=content[:200] or None,
        )
    return ModelHealthCheckItem(
        name="short_chat",
        status="passed",
        latency_ms=latency_ms,
        message=f"ping 正常（{latency_ms}ms）",
        suggestion=None,
        raw_preview=content[:200] or None,
    )


async def _probe_json_output(client, row, target_model, db: AsyncSession) -> ModelHealthCheckItem:
    """P15 / P0-HEALTH-1: ask the model to output STRICT JSON.

    The prompt explicitly forbids markdown fences and leading prose.
    Validation: strip optional ``` fences, then ``json.loads``. If the
    parsed object has ``ok == true`` and the right ``name`` we pass.
    """
    prompt = (
        "只输出 JSON，不要 Markdown，不要解释，不要前后缀。\n"
        "请返回:\n"
        '{"ok": true, "name": "json_test", "score": 100}'
    )
    messages = [LLMMessage(role="user", content=prompt)]
    latency_ms, content, err = await _run_probe(
        client, row, target_model,
        db=db,
        probe_name="json_output",
        messages=messages, max_tokens=200,
        response_format={"type": "json_object"},
        probe_timeout=_HEALTHY_MS_PER_TEST["json_output"] / 1000 + 5,
    )
    if err:
        return ModelHealthCheckItem(
            name="json_output",
            status="failed",
            latency_ms=latency_ms,
            message=err.split("|", 1)[0].strip(),
            suggestion="请检查网络、API Key 和 Base URL。",
            raw_preview=None,
        )
    cleaned = (content or "").strip()
    # Strip markdown fences if the model still wrapped it.
    if cleaned.startswith("```"):
        # drop first line (```json or ```)
        first_nl = cleaned.find("\n")
        if first_nl != -1:
            cleaned = cleaned[first_nl + 1 :]
        if cleaned.endswith("```"):
            cleaned = cleaned[: -3]
        cleaned = cleaned.strip()
        if not cleaned.startswith("{"):
            return ModelHealthCheckItem(
                name="json_output",
                status="failed",
                latency_ms=latency_ms,
                message="输出包含 Markdown 代码围栏",
                suggestion="该模型未严格遵守 JSON 输出要求，建议避免用于 Planner / Critic / Memory。",
                raw_preview=(content or "")[:500],
            )
    try:
        obj = json.loads(cleaned)
    except Exception as exc:
        return ModelHealthCheckItem(
            name="json_output",
            status="failed",
            latency_ms=latency_ms,
            message=f"JSON 解析失败：{exc}",
            suggestion="该模型未严格遵守 JSON 输出要求，建议避免用于 Planner / Critic / Memory。",
            raw_preview=(content or "")[:500],
        )
    if not isinstance(obj, dict) or obj.get("ok") is not True:
        return ModelHealthCheckItem(
            name="json_output",
            status="failed",
            latency_ms=latency_ms,
            message="缺少 ok=true 字段或不是 JSON 对象",
            suggestion="检查模型是否理解 JSON contract。",
            raw_preview=(content or "")[:500],
        )
    if obj.get("name") != "json_test":
        return ModelHealthCheckItem(
            name="json_output",
            status="warning",
            latency_ms=latency_ms,
            message=f"name 字段错误：{obj.get('name')!r}",
            suggestion="模型能输出 JSON，但 schema 跟随不稳定。",
            raw_preview=(content or "")[:500],
        )
    budget = _HEALTHY_MS_PER_TEST["json_output"]
    if latency_ms > budget:
        return ModelHealthCheckItem(
            name="json_output",
            status="warning",
            latency_ms=latency_ms,
            message=f"JSON 输出通过但偏慢（{latency_ms}ms > {budget // 1000}s）",
            suggestion="可用于 Planner / Critic / Memory，但流水线整体可能变慢。",
            raw_preview=(content or "")[:200],
        )
    return ModelHealthCheckItem(
        name="json_output",
        status="passed",
        latency_ms=latency_ms,
        message=f"JSON 输出通过（{latency_ms}ms）",
        suggestion=None,
        raw_preview=(content or "")[:200],
    )


async def _probe_critic_schema(client, row, target_model, db: AsyncSession) -> ModelHealthCheckItem:
    """P15 / P0-HEALTH-1: ask the model to act as a Critic and return
    the full Critic JSON schema. We validate field-by-field so the UI
    can show *which* field the model got wrong."""
    prompt = (
        "你是小说审稿 Agent。只输出 JSON，不要 Markdown，不要解释。\n"
        "请按下面 schema 评价一段测试文本（极简文本，无冲突）：\n"
        "{\n"
        '  "total": 0,\n'
        '  "dimension_scores": {"plot": 0, "character": 0, "continuity": 0, "style": 0, "hook": 0},\n'
        '  "issues": [],\n'
        '  "rewrite_required": false\n'
        "}\n"
        "测试文本：\n"
        "沈落站在雨里。他很生气。他决定明天再说。\n"
    )
    messages = [LLMMessage(role="user", content=prompt)]
    latency_ms, content, err = await _run_probe(
        client, row, target_model,
        db=db,
        probe_name="critic_schema",
        messages=messages, max_tokens=600,
        response_format={"type": "json_object"},
        probe_timeout=_HEALTHY_MS_PER_TEST["critic_schema"] / 1000 + 5,
    )
    if err:
        return ModelHealthCheckItem(
            name="critic_schema",
            status="failed",
            latency_ms=latency_ms,
            message=err.split("|", 1)[0].strip(),
            suggestion="请检查网络、API Key 和 Base URL。",
            raw_preview=None,
        )
    cleaned = (content or "").strip()
    if cleaned.startswith("```"):
        first_nl = cleaned.find("\n")
        if first_nl != -1:
            cleaned = cleaned[first_nl + 1 :]
        if cleaned.endswith("```"):
            cleaned = cleaned[: -3]
        cleaned = cleaned.strip()
    try:
        obj = json.loads(cleaned)
    except Exception as exc:
        return ModelHealthCheckItem(
            name="critic_schema",
            status="failed",
            latency_ms=latency_ms,
            message=f"Critic JSON 解析失败：{exc}",
            suggestion="该模型不能用作 Critic 角色——会直接导致流水线失败。",
            raw_preview=(content or "")[:500],
        )
    missing: list[str] = []
    if not isinstance(obj, dict):
        missing.append("(root 不是 JSON 对象)")
    else:
        if not isinstance(obj.get("total"), (int, float)):
            missing.append("total")
        ds = obj.get("dimension_scores")
        if not isinstance(ds, dict):
            missing.append("dimension_scores")
        else:
            for k in ("plot", "character", "continuity", "style", "hook"):
                if not isinstance(ds.get(k), (int, float)):
                    missing.append(f"dimension_scores.{k}")
        if not isinstance(obj.get("issues"), list):
            missing.append("issues")
        if not isinstance(obj.get("rewrite_required"), bool):
            missing.append("rewrite_required")
    if missing:
        return ModelHealthCheckItem(
            name="critic_schema",
            status="failed",
            latency_ms=latency_ms,
            message=f"Critic schema 缺字段：{', '.join(missing)}",
            suggestion="该模型不能用作 Critic 角色，绑定到 Critic 会导致流水线反复返工。",
            raw_preview=(content or "")[:500],
        )
    budget = _HEALTHY_MS_PER_TEST["critic_schema"]
    if latency_ms > budget:
        return ModelHealthCheckItem(
            name="critic_schema",
            status="warning",
            latency_ms=latency_ms,
            message=f"Critic schema 通过但偏慢（{latency_ms}ms > {budget // 1000}s）",
            suggestion="可继续用于 Critic，但流水线总时长会变长。",
            raw_preview=(content or "")[:200],
        )
    return ModelHealthCheckItem(
        name="critic_schema",
        status="passed",
        latency_ms=latency_ms,
        message=f"Critic schema 通过（{latency_ms}ms）",
        suggestion=None,
        raw_preview=(content or "")[:200],
    )


async def _probe_long_text(client, row, target_model, db: AsyncSession) -> ModelHealthCheckItem:
    """P15 / P0-HEALTH-1: ask the model to output ≥ 1000 Chinese chars.

    We don't measure "quality" — we measure "can it actually generate
    a long enough chunk of prose without truncating at 200 chars".
    A model that returns 200 chars of placeholder is unusable for
    Draft / Rewrite (which need 2K-6K tokens)."""
    # P0-MODEL-11: tightened the long_text budget. We used to ask
    # for 1200 chars (max_tokens=2000) and a 30+10=40s timeout.
    # With step-3.7-flash at ~18 tok/s the model needed ~80s to
    # produce 1200 chars of prose, so the probe *always* hit the
    # timeout and the role matrix flagged Draft/Rewrite as
    # "unsuitable (failed: long_text)" — even though the model is
    # perfectly capable of writing 600 chars of passable prose in
    # 10s. The role-binding matrix's goal is to catch "model
    # truncates at 200 chars" / "model refuses to write", not to
    # grade writing speed, so 600 chars / max_tokens=800 is a more
    # honest bar.
    prompt = (
        "请写一段约 600 字的中文小说片段，主角是一个刚入门派的少年，"
        "题材是玄幻，重点是：被师兄误会、试炼失败、得到神秘指引三件事连贯。\n"
        "要求：纯散文，不要 JSON，不要列表，不要解释。"
    )
    messages = [LLMMessage(role="user", content=prompt)]
    latency_ms, content, err = await _run_probe(
        client, row, target_model, db=db, probe_name="long_text", messages=messages, max_tokens=800,
        probe_timeout=_HEALTHY_MS_PER_TEST["long_text"] / 1000 + 10,
    )
    if err:
        return ModelHealthCheckItem(
            name="long_text",
            status="failed",
            latency_ms=latency_ms,
            message=err.split("|", 1)[0].strip(),
            suggestion="请检查网络、API Key 和 Base URL。",
            raw_preview=None,
        )
    chars = len(content or "")
    if chars < 500:
        return ModelHealthCheckItem(
            name="long_text",
            status="failed",
            latency_ms=latency_ms,
            message=f"长文本输出不足：{chars} 字符 < 500",
            suggestion="该模型不能用于 Draft / Rewrite，单章输出太短。",
            raw_preview=(content or "")[:500],
        )
    if chars < 600:
        return ModelHealthCheckItem(
            name="long_text",
            status="warning",
            latency_ms=latency_ms,
            message=f"长文本输出勉强：{chars} 字符（接近 600 目标）",
            suggestion="可继续用于 Draft / Rewrite，但建议观察字数达标率。",
            raw_preview=(content or "")[:200],
        )
    budget = _HEALTHY_MS_PER_TEST["long_text"]
    if latency_ms > budget:
        return ModelHealthCheckItem(
            name="long_text",
            status="warning",
            latency_ms=latency_ms,
            message=f"长文本通过但偏慢（{latency_ms}ms > {budget // 1000}s，{chars} 字符）",
            suggestion="可继续用于 Draft / Rewrite，但流水线总时长会变长。",
            raw_preview=(content or "")[:200],
        )
    return ModelHealthCheckItem(
        name="long_text",
        status="passed",
        latency_ms=latency_ms,
        message=f"长文本通过：{chars} 字符（{latency_ms}ms）",
        suggestion=None,
        raw_preview=(content or "")[:200],
    )


def _aggregate_health(
    results: list[ModelHealthCheckItem],
    fatal: tuple[HealthStatus, str, str | None] | None,
) -> tuple[HealthStatus, str, str | None, int, int]:
    """Combine per-test results into the top-level (status, message, suggestion,
    total_latency_ms, score)."""
    if fatal is not None:
        status, msg, sug = fatal
        return status, f"健康检查提前终止：{msg}", sug, sum(r.latency_ms for r in results), 0

    passed = sum(1 for r in results if r.status == "passed")
    warned = sum(1 for r in results if r.status == "warning")
    failed = sum(1 for r in results if r.status == "failed")
    skipped = sum(1 for r in results if r.status == "skipped")
    total_latency = sum(r.latency_ms for r in results)
    # 0..100, weighted by test importance. critic_schema and long_text
    # are worth more because they're the tests that actually catch
    # pipeline-stopping bugs.
    weights = {
        "short_chat": 10,
        "json_output": 25,
        "critic_schema": 35,
        "long_text": 30,
    }
    earned = 0
    max_possible = sum(weights.values())
    for r in results:
        w = weights.get(r.name, 10)
        if r.status == "passed":
            earned += w
        elif r.status == "warning":
            earned += w * 0.6
    score = int(round(100 * earned / max_possible)) if max_possible else 0

    if failed > 0:
        # At least one test failed → degraded. The user can still use
        # the model for roles that don't depend on the failed test
        # (see recommended_roles).
        status: HealthStatus = "degraded"
        first_failed = next((r for r in results if r.status == "failed"), None)
        msg = f"{failed} 项测试未通过：{first_failed.name}（{first_failed.message}）" if first_failed else f"{failed} 项测试未通过"
        sug = first_failed.suggestion if first_failed else "查看下方测试详情。"
    elif warned > 0 or skipped > 0:
        status = "degraded"
        first_warn = next((r for r in results if r.status == "warning"), None)
        if first_warn:
            msg = f"通过但有 {warned} 项偏慢：{first_warn.name}（{first_warn.message}）"
            sug = first_warn.suggestion
        else:
            msg = f"通过但有 {skipped} 项被跳过"
            sug = None
    else:
        status = "healthy"
        msg = f"全部 {passed} 项测试通过（{total_latency}ms）"
        sug = None

    return status, msg, sug, total_latency, score


def _derive_recommended_roles(results: list[ModelHealthCheckItem]) -> dict[str, str]:
    """For each known role, decide if the model is suitable / risky /
    unsuitable. The UI uses this to mark Critic-bound risky models in
    red so the operator notices before the next pipeline run."""
    by_name = {r.name: r for r in results}
    out: dict[str, str] = {}
    for role, req in _ROLE_REQUIREMENTS.items():
        need_results = [by_name.get(n) for n in req["need"]]
        if any(r is None or r.status == "skipped" for r in need_results):
            out[role] = "unknown"
            continue
        bad = [r for r in need_results if r.status == "failed"]
        warn = [r for r in need_results if r.status == "warning"]
        if bad:
            failed_names = ", ".join(sorted({r.name for r in bad}))  # type: ignore[union-attr]
            out[role] = f"unsuitable (failed: {failed_names})"
        elif warn:
            warn_names = ", ".join(sorted({r.name for r in warn}))  # type: ignore[union-attr]
            out[role] = f"risky (slow: {warn_names})"
        else:
            out[role] = "suitable"
    return out


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


# ── P4-Model-Failover: Provider 熔断重置 ──────────────────

@router.post("/providers/{provider_id}/circuit/reset")
async def reset_provider_circuit(
    provider_id: int, db: AsyncSession = Depends(get_db),
) -> dict:
    """手动解除 Provider 熔断."""
    from app.services.model_circuit_breaker import CircuitBreakerService
    from app.schemas.model_failover import CircuitResetResponse
    try:
        provider = await CircuitBreakerService().reset_circuit(db, provider_id)
        await db.commit()
        return CircuitResetResponse(
            ok=True,
            provider_id=provider_id,
            circuit_state=provider.circuit_state,
            message=f"Provider {provider.name} 熔断已重置为 closed",
        ).model_dump()
    except ValueError as e:
        from fastapi import HTTPException
        raise HTTPException(404, str(e))


@router.post("/providers/{provider_id}/health/full")
async def full_provider_health(
    provider_id: int, db: AsyncSession = Depends(get_db),
) -> dict:
    """完整健康探针 (list_models + short chat + json + long)."""
    from app.services.provider_health import ProviderHealthService
    from app.schemas.model_failover import ProviderHealthFullResponse, ProviderHealthFullModelItem
    provider = await db.get(ModelProvider, provider_id)
    if provider is None:
        from fastapi import HTTPException
        raise HTTPException(404, f"Provider {provider_id} 不存在")

    text_models = [
        m for m in (provider.model_list or [])
        if is_text_role_model_compatible("health_check", m)
    ]
    original_default = provider.default_model
    if provider.default_model and not is_text_role_model_compatible("health_check", provider.default_model):
        provider.default_model = text_models[0] if text_models else None
    if not provider.default_model and text_models:
        provider.default_model = text_models[0]

    if not provider.default_model:
        provider.last_health_status = "unknown_error"
        provider.last_health_message = "没有可用于文本 Agent 的模型；已跳过生图/视频/音频模型。"
        provider.last_health_latency_ms = 0
        provider.last_health_at = datetime.utcnow()
        provider.default_model = original_default
        await db.commit()
        return ProviderHealthFullResponse(
            provider_id=provider_id,
            status=provider.last_health_status,
            health_score=0,
            latency_ms=0,
            models=[],
        ).model_dump()

    result = await ProviderHealthService().check_provider(db, provider, lightweight=False)
    if original_default and original_default != provider.default_model:
        provider.default_model = original_default
    await db.commit()

    # 构建模型结果
    hf = provider.last_health_full or {}
    model_items = []
    for m in [m for m in (provider.model_list or []) if is_text_role_model_compatible("health_check", m)][:20]:
        mr = hf.get("details", {}).get(m, {})
        model_items.append(ProviderHealthFullModelItem(
            model=m,
            available=True,
            json_score=mr.get("json_score"),
            long_output_score=mr.get("long_output_score"),
            speed_score=mr.get("speed_score"),
            recommended_roles=mr.get("recommended_roles", []),
        ))

    return ProviderHealthFullResponse(
        provider_id=provider_id,
        status=provider.last_health_status or "unknown",
        health_score=provider.health_score or 0.75,
        latency_ms=provider.last_health_latency_ms,
        models=model_items,
    ).model_dump()
