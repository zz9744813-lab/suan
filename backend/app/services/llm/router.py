"""LLMRouter: map agent role -> provider/model using DB-backed assignments.

P2-Model-Failover: resolve() 优先走新 AgentModelBinding + ModelSelector,
兼容旧 ModelRoleAssignment. chat() 增加 fallback 重试链.
"""
from __future__ import annotations

import asyncio
from collections import defaultdict, deque
import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
import time
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.errors import bad_request, model_connection_error
from app.models.model_provider import ModelProvider, ModelRoleAssignment
from app.services.llm.client import (
    LLMCallResult,
    LLMClient,
    LLMMessage,
    LLMRequest,
    LLMAuthError,
    LLMConnectionError,
    LLMError,
    LLMRateLimitError,
    LLMResponseError,
)
from app.services.llm.error_classifier import classify_llm_exception
from app.services.model_capability import LEGACY_ROLE_TO_AGENT_KEY
from app.services.model_call_recorder import ModelCallRecorder
from app.services.model_selector import ModelCandidate, get_model_selector

logger = logging.getLogger(__name__)

# 单次 Agent 调用内最多 fallback 次数
MAX_FALLBACK_ATTEMPTS = 2
DEFAULT_TASK_RPM = 5


class _LLMRateLimiter:
    """Small in-process RPM limiter keyed by task/provider.

    It is deliberately conservative and process-local. It prevents the
    local worker from flooding one provider when DeepStudy runs chapter
    work concurrently. Cache hits bypass this limiter because no upstream
    request is made.
    """

    def __init__(self, rpm: int = DEFAULT_TASK_RPM) -> None:
        self.rpm = max(1, rpm)
        self.window_seconds = 60.0
        self._locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._timestamps: dict[str, deque[float]] = defaultdict(deque)

    async def wait(self, key: str) -> None:
        lock = self._locks[key]
        async with lock:
            while True:
                now = time.monotonic()
                timestamps = self._timestamps[key]
                while timestamps and now - timestamps[0] >= self.window_seconds:
                    timestamps.popleft()
                if len(timestamps) < self.rpm:
                    timestamps.append(now)
                    return
                sleep_for = self.window_seconds - (now - timestamps[0])
                await asyncio.sleep(max(0.05, sleep_for))


_rate_limiter = _LLMRateLimiter()


def _stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _semantic_request_payload(
    *,
    provider_id: int | None,
    provider_name: str | None,
    model_name: str,
    agent_role_key: str | None,
    role: str,
    request: LLMRequest,
) -> dict[str, Any]:
    return {
        "schema": 1,
        "provider_id": provider_id,
        "provider_name": provider_name,
        "model_name": model_name,
        "agent_role_key": agent_role_key,
        "role": role,
        "messages": [{"role": m.role, "content": m.content} for m in request.messages],
        "temperature": request.temperature,
        "max_tokens": request.max_tokens,
        "response_format": request.response_format,
        "extra": request.extra,
    }


def _request_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(_stable_json(payload).encode("utf-8")).hexdigest()


def _request_id(hash_value: str) -> str:
    return f"llm_{hash_value[:48]}"


def _is_real_api_text_model(provider: ModelProvider, model_name: str | None) -> bool:
    base_url = (provider.base_url or "").lower()
    if base_url.startswith("mock://"):
        return False
    if "localhost" in base_url or "127.0.0.1" in base_url or base_url.startswith("http://local"):
        return False
    if not provider.api_key:
        return False
    from app.services.model_selector import is_text_role_model_compatible

    return is_text_role_model_compatible("legacy_text_role", model_name or "")


@dataclass
class ResolvedCall:
    provider: ModelProvider
    model: str
    temperature: float
    max_tokens: int
    extra_body: dict[str, Any] | None = None
    # P2-Model-Failover 新增
    selection_mode: str = "manual"
    selection_score: float | None = None
    selection_reason: str | None = None


class LLMRouter:
    def __init__(self, client: LLMClient) -> None:
        self.client = client

    def _build_cache_identity(
        self,
        *,
        resolved: ResolvedCall,
        role: str,
        request: LLMRequest,
    ) -> tuple[str, str, dict[str, Any], str | None]:
        agent_key = LEGACY_ROLE_TO_AGENT_KEY.get(role) or role
        payload = _semantic_request_payload(
            provider_id=getattr(resolved.provider, "id", None),
            provider_name=getattr(resolved.provider, "name", None),
            model_name=resolved.model,
            agent_role_key=agent_key,
            role=role,
            request=request,
        )
        hash_value = _request_hash(payload)
        return _request_id(hash_value), hash_value, payload, agent_key

    async def _lookup_cache(self, db: AsyncSession, request_id: str):
        if not isinstance(db, AsyncSession):
            return None
        try:
            from app.models.llm_cache import LLMCacheEntry

            result = await db.execute(
                select(LLMCacheEntry).where(LLMCacheEntry.request_id == request_id)
            )
            entry = result.scalar_one_or_none()
            if isinstance(entry, LLMCacheEntry):
                return entry
        except Exception as exc:
            logger.debug("LLM cache lookup skipped: %s", exc)
        return None

    async def _store_cache_entry(
        self,
        db: AsyncSession,
        *,
        request_id: str,
        request_hash: str,
        request_payload: dict[str, Any],
        resolved: ResolvedCall,
        agent_role_key: str | None,
        step_key: str | None,
        result: LLMCallResult,
    ) -> None:
        if not isinstance(db, AsyncSession):
            return
        try:
            from app.models.llm_cache import LLMCacheEntry

            existing = await self._lookup_cache(db, request_id)
            if existing is not None:
                return
            entry = LLMCacheEntry(
                request_id=request_id,
                request_hash=request_hash,
                provider_id=getattr(resolved.provider, "id", None),
                provider_name=getattr(resolved.provider, "name", None),
                model_name=resolved.model,
                agent_role_key=agent_role_key,
                step_key=step_key,
                request_json=request_payload,
                response_content=result.content,
                response_raw=result.raw,
                response_model=result.model,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                cost_usd=result.cost_usd,
                duration_ms=result.duration_ms,
            )
            async with db.begin_nested():
                db.add(entry)
                await db.flush()
        except Exception as exc:
            logger.debug("LLM cache store skipped: %s", exc)

    def _result_from_cache(self, entry) -> LLMCallResult:
        raw = dict(entry.response_raw or {})
        raw["_cache_hit"] = True
        raw["_cached_request_id"] = entry.request_id
        return LLMCallResult(
            content=entry.response_content or "",
            model=entry.response_model or entry.model_name or "",
            input_tokens=0,
            output_tokens=0,
            cost_usd=0.0,
            duration_ms=0,
            raw=raw,
        )

    async def _touch_cache_hit(self, db: AsyncSession, entry) -> None:
        if not isinstance(db, AsyncSession):
            return
        try:
            entry.hit_count = (entry.hit_count or 0) + 1
            entry.last_hit_at = datetime.utcnow()
            entry.updated_at = datetime.utcnow()
            await db.flush()
        except Exception as exc:
            logger.debug("LLM cache hit touch skipped: %s", exc)

    async def _wait_for_rate_limit(
        self,
        *,
        resolved: ResolvedCall,
        task_type: str | None,
        step_key: str | None,
        agent_role_key: str | None,
    ) -> None:
        provider_id = getattr(resolved.provider, "id", None) or getattr(resolved.provider, "name", "unknown")
        bucket = task_type or step_key or agent_role_key or "llm"
        await _rate_limiter.wait(f"{bucket}:{provider_id}")

    async def resolve(self, db: AsyncSession, role: str) -> ResolvedCall:
        """解析角色 → 模型. 优先走 ModelSelector, 兼容旧 ModelRoleAssignment."""
        # ── P2: 优先走新 AgentModelBinding + ModelSelector ──
        agent_key = LEGACY_ROLE_TO_AGENT_KEY.get(role)
        if agent_key:
            try:
                selected = await get_model_selector().select_for_agent(
                    db, agent_role_key=agent_key, legacy_role=role,
                )
                return ResolvedCall(
                    provider=selected.provider,
                    model=selected.model_name,
                    temperature=selected.temperature,
                    max_tokens=selected.max_tokens,
                    extra_body=selected.extra_body,
                    selection_mode=selected.selection_mode,
                    selection_score=selected.selection_score,
                    selection_reason=selected.selection_reason,
                )
            except Exception as exc:
                # ModelSelector 失败, 降级到旧逻辑
                logger.warning(f"ModelSelector failed for {agent_key}: {exc}, falling back to legacy")

        # ── 旧逻辑: ModelRoleAssignment ──
        return await self._resolve_legacy(db, role)

    async def _resolve_legacy(self, db: AsyncSession, role: str) -> ResolvedCall:
        """旧 ModelRoleAssignment 解析逻辑 (保留兼容)."""
        stmt = (
            select(ModelRoleAssignment)
            .options(selectinload(ModelRoleAssignment.provider))
            .where(ModelRoleAssignment.role == role)
        )
        result = (
            await db.execute(stmt.order_by(ModelRoleAssignment.id.asc()))
        ).scalars().first()
        if (
            result and result.provider and result.provider.enabled
            and _is_real_api_text_model(result.provider, result.model)
        ):
            return ResolvedCall(
                provider=result.provider,
                model=result.model,
                temperature=result.temperature,
                max_tokens=result.max_tokens,
                selection_mode="manual",
                selection_reason=f"旧绑定: {result.provider.name}/{result.model}",
            )
        providers = (await db.execute(
            select(ModelProvider)
            .where(ModelProvider.enabled.is_(True))
            .order_by(ModelProvider.id.asc())
        )).scalars().all()
        for first in providers:
            models = list(first.model_list or [])
            if first.default_model and first.default_model not in models:
                models.insert(0, first.default_model)
            model = next((m for m in models if _is_real_api_text_model(first, m)), None)
            if not model:
                continue
            return ResolvedCall(
                provider=first,
                model=model,
                temperature=0.8,
                max_tokens=2048,
                selection_mode="auto",
                selection_reason=f"legacy API fallback: {first.name}/{model}",
            )

        raise bad_request(
            f"Role '{role}' has no real API text model available",
            suggestion="Configure an API-key chat/text provider; stub, local, image, video, and audio models are not valid for text agents.",
        )

        # fallback: first enabled provider
        stmt_first = (
            select(ModelProvider)
            .where(
                ModelProvider.enabled.is_(True),
                ~ModelProvider.base_url.like("mock://%"),
            )
            .order_by(ModelProvider.id.asc())
            .limit(1)
        )
        first = (await db.execute(stmt_first)).scalars().first()
        if first is None:
            raise bad_request(
                f"角色 '{role}' 没有专属模型绑定，且当前没有真实可用的 Provider",
                suggestion="请在「模型配置」页添加一个真实 Provider，并把该角色绑定到该 Provider 的模型。",
            )
        if not first.default_model:
            raise bad_request(
                f"Provider '{first.name}' 缺少默认模型",
                suggestion="请在 Provider 中设置 default_model 或为该角色绑定具体模型。",
            )
        return ResolvedCall(
            provider=first,
            model=first.default_model,
            temperature=0.8,
            max_tokens=2048,
            selection_mode="auto",
            selection_reason=f"兜底: {first.name}/{first.default_model}",
        )

    async def chat(
        self,
        db: AsyncSession,
        role: str,
        messages: list[LLMMessage],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        response_format: dict[str, str] | None = None,
        extra: dict[str, Any] | None = None,
        stream: bool = True,
        task_id: int | None = None,
        chapter_id: int | None = None,
        step_key: str | None = None,
        agent_step_id: int | None = None,
        project_id: int | None = None,
        task_type: str | None = None,
    ) -> tuple[ResolvedCall, LLMCallResult]:
        """调用 LLM, 支持 fallback 链.

        如果主模型失败且 Agent 允许 fallback, 自动切换候选模型.
        """
        resolved = await self.resolve(db, role)
        request = LLMRequest(
            model=resolved.model,
            messages=messages,
            temperature=temperature if temperature is not None else resolved.temperature,
            max_tokens=max_tokens if max_tokens is not None else resolved.max_tokens,
            response_format=response_format,
            extra=extra or {},
            stream=stream,
        )
        request_id, request_hash, request_payload, agent_key = self._build_cache_identity(
            resolved=resolved,
            role=role,
            request=request,
        )
        cache_enabled = not bool((extra or {}).get("disable_cache"))
        recorder = ModelCallRecorder()
        if cache_enabled:
            cache_entry = await self._lookup_cache(db, request_id)
            if cache_entry is not None:
                event = await recorder.record_selection(
                    db,
                    provider_id=resolved.provider.id,
                    model_name=resolved.model,
                    agent_role_key=agent_key,
                    selection_mode=resolved.selection_mode,
                    selection_score=resolved.selection_score,
                    selection_reason=resolved.selection_reason,
                    project_id=project_id,
                    task_id=task_id,
                    chapter_id=chapter_id,
                    agent_step_id=agent_step_id,
                    step_key=step_key,
                    provider_name=resolved.provider.name,
                    request_id=request_id,
                    cache_hit=True,
                    event_type="cache_hit",
                    event_category="cache",
                    level="success",
                )
                await recorder.record_cache_hit(
                    db,
                    event,
                    input_tokens=cache_entry.input_tokens or 0,
                    output_tokens=cache_entry.output_tokens or 0,
                )
                await self._touch_cache_hit(db, cache_entry)
                return resolved, self._result_from_cache(cache_entry)

        await self._wait_for_rate_limit(
            resolved=resolved,
            task_type=task_type,
            step_key=step_key,
            agent_role_key=agent_key,
        )

        # ── 记录选择事件 ──
        event = await recorder.record_selection(
            db,
            provider_id=resolved.provider.id,
            model_name=resolved.model,
            agent_role_key=agent_key,
            selection_mode=resolved.selection_mode,
            selection_score=resolved.selection_score,
            selection_reason=resolved.selection_reason,
            project_id=project_id,
            task_id=task_id,
            chapter_id=chapter_id,
            agent_step_id=agent_step_id,
            step_key=step_key,
            provider_name=resolved.provider.name,
            request_id=request_id,
            cache_hit=False,
        )

        # ── 主模型调用 ──
        try:
            result = await self.client.chat(
                base_url=resolved.provider.base_url,
                api_key=resolved.provider.api_key,
                request=request,
                provider_extra=resolved.provider.extra or {},
            )
            await recorder.record_success(
                db, event,
                latency_ms=result.duration_ms,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                cost_usd=result.cost_usd,
            )
            if cache_enabled:
                await self._store_cache_entry(
                    db,
                    request_id=request_id,
                    request_hash=request_hash,
                    request_payload=request_payload,
                    resolved=resolved,
                    agent_role_key=agent_key,
                    step_key=step_key,
                    result=result,
                )
            return resolved, result

        except (LLMAuthError, LLMConnectionError, LLMResponseError,
                LLMRateLimitError, LLMError) as exc:
            failure_type = classify_llm_exception(exc)
            await recorder.record_failure(db, event, failure_type, str(exc)[:2000])

            # ── 熔断处理 ──
            from app.services.model_circuit_breaker import CircuitBreakerService
            cb = CircuitBreakerService()
            await cb.record_failure(
                db, resolved.provider.id, resolved.model,
                LEGACY_ROLE_TO_AGENT_KEY.get(role),
                failure_type, str(exc)[:2000],
            )

            # ── 尝试 fallback ──
            # P0 返工 Phase 5.3 (验收 A8): Agent 锁死模型 = selection_mode="manual"
            # 必须后端硬锁 — 不允许 fallback。即使主模型 401/timeout 也不
            # 自动换模型, 直接失败抛回给上游。下面的 `!= "manual"` 是
            # 唯一的 gate, 改了这里就改了 spec, 改完记得跑 test_provider_lock。
            agent_key = LEGACY_ROLE_TO_AGENT_KEY.get(role)
            if agent_key and resolved.selection_mode != "manual":
                fallback_result = await self._try_fallback(
                    db, role, agent_key, messages,
                    temperature=temperature, max_tokens=max_tokens,
                    response_format=response_format, extra=extra,
                    stream=stream, recorder=recorder,
                    primary_failure_type=failure_type,
                    primary_provider_name=resolved.provider.name,
                    primary_model_name=resolved.model,
                    project_id=project_id,
                    task_id=task_id,
                    chapter_id=chapter_id,
                    step_key=step_key,
                    agent_step_id=agent_step_id,
                    task_type=task_type,
                )
                if fallback_result is not None:
                    return fallback_result

            # ── 无 fallback 或 fallback 也失败 ──
            if isinstance(exc, LLMAuthError):
                raise model_connection_error(
                    f"模型鉴权失败（{resolved.provider.name}）: {exc}",
                    suggestion="请检查 API Key 是否有效或已过期。",
                ) from exc
            elif isinstance(exc, LLMConnectionError):
                raise model_connection_error(
                    f"无法连接模型（{resolved.provider.name}）: {exc}",
                    suggestion="请检查 Base URL 是否可访问，或网络是否通畅。",
                ) from exc
            elif isinstance(exc, LLMResponseError):
                raise model_connection_error(
                    f"模型返回异常（{resolved.provider.name}）: {exc}",
                    suggestion="请稍后重试，或更换模型。",
                ) from exc
            else:
                raise model_connection_error(f"模型调用失败: {exc}") from exc

    async def _try_fallback(
        self,
        db: AsyncSession,
        role: str,
        agent_key: str,
        messages: list[LLMMessage],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        response_format: dict[str, str] | None = None,
        extra: dict[str, Any] | None = None,
        stream: bool = True,
        recorder: Any = None,
        primary_failure_type: str | None = None,
        primary_provider_name: str | None = None,
        primary_model_name: str | None = None,
        project_id: int | None = None,
        task_id: int | None = None,
        chapter_id: int | None = None,
        step_key: str | None = None,
        agent_step_id: int | None = None,
        task_type: str | None = None,
    ) -> tuple[ResolvedCall, LLMCallResult] | None:
        """尝试 fallback 到候选列表中的下一个可用模型.

        P0-Model-Failover fix: 不再只试一次, 而是循环遍历候选列表
        (最多 MAX_FALLBACK_ATTEMPTS 次), 跳过已失败的 provider/model 组合.
        """
        try:
            selected = await get_model_selector().select_for_agent(
                db, agent_role_key=agent_key, legacy_role=role,
                force_fallback=True,
            )
        except Exception:
            return None

        # 收集主模型的 provider_id + model_name (在调用方已失败, 排除之)
        # candidates 列表已按分数降序排列, 过滤掉主模型取前 MAX_FALLBACK_ATTEMPTS 个
        primary_provider_id = selected.provider.id
        primary_model_name = selected.model_name

        # 从候选列表取 fallback 序列
        # (排除主模型自身, 保留其余最多 MAX_FALLBACK_ATTEMPTS 个)
        fallback_candidates = [
            c for c in selected.candidates
            if not (c.provider_id == primary_provider_id and c.model_name == primary_model_name)
        ][:MAX_FALLBACK_ATTEMPTS]

        # 如果候选列表仅有一个模型 (就是主模型), 就没有可用 fallback
        if not fallback_candidates:
            # 仍然把 selected 自身作为第一个候选尝试
            # (选择器可能已挑了不同于主模型的最优候选)
            fallback_candidates = [
                ModelCandidate(
                    provider_id=selected.provider.id,
                    provider_name=selected.provider.name,
                    base_url=selected.provider.base_url,
                    api_key=selected.provider.api_key,
                    model_name=selected.model_name,
                    score=selected.selection_score,
                    reason=selected.selection_reason,
                )
            ]

        # 已失败的 (provider_id, model) 集合, 避免重试
        failed_set: set[tuple[int, str]] = set()

        for attempt_no, cand in enumerate(fallback_candidates, start=1):
            if (cand.provider_id, cand.model_name) in failed_set:
                continue

            # 实时加载 provider (候选里只有 id, 需要 ORM 对象)
            from app.models.model_provider import ModelProvider as _MP
            fb_provider = await db.get(_MP, cand.provider_id)
            if fb_provider is None or not fb_provider.enabled:
                logger.debug("fallback skip: provider %d not found/disabled", cand.provider_id)
                continue

            fallback_resolved = ResolvedCall(
                provider=fb_provider,
                model=cand.model_name,
                temperature=cand.temperature or selected.temperature,
                max_tokens=cand.max_tokens or selected.max_tokens,
                extra_body=cand.extra_body or selected.extra_body,
                selection_mode="manual_with_fallback",
                selection_score=cand.score,
                selection_reason=f"fallback#{attempt_no}: {cand.reason}",
            )

            request = LLMRequest(
                model=fallback_resolved.model,
                messages=messages,
                temperature=temperature if temperature is not None else fallback_resolved.temperature,
                max_tokens=max_tokens if max_tokens is not None else fallback_resolved.max_tokens,
                response_format=response_format,
                extra=extra or {},
                stream=stream,
            )
            request_id, request_hash, request_payload, fallback_agent_key = self._build_cache_identity(
                resolved=fallback_resolved,
                role=role,
                request=request,
            )
            cache_enabled = not bool((extra or {}).get("disable_cache"))
            if cache_enabled:
                cache_entry = await self._lookup_cache(db, request_id)
                if cache_entry is not None:
                    event = None
                    if recorder:
                        event = await recorder.record_selection(
                            db,
                            provider_id=fallback_resolved.provider.id,
                            model_name=fallback_resolved.model,
                            agent_role_key=agent_key or fallback_agent_key,
                            selection_mode="manual_with_fallback",
                            selection_score=fallback_resolved.selection_score,
                            selection_reason=f"fallback#{attempt_no}: cache hit",
                            project_id=project_id,
                            task_id=task_id,
                            chapter_id=chapter_id,
                            step_key=step_key,
                            agent_step_id=agent_step_id,
                            provider_name=fallback_resolved.provider.name,
                            request_id=request_id,
                            cache_hit=True,
                            event_type="cache_hit",
                            event_category="cache",
                            level="success",
                        )
                    if recorder and event:
                        await recorder.record_cache_hit(
                            db,
                            event,
                            input_tokens=cache_entry.input_tokens or 0,
                            output_tokens=cache_entry.output_tokens or 0,
                        )
                    await self._touch_cache_hit(db, cache_entry)
                    return fallback_resolved, self._result_from_cache(cache_entry)

            await self._wait_for_rate_limit(
                resolved=fallback_resolved,
                task_type=task_type,
                step_key=step_key,
                agent_role_key=agent_key or fallback_agent_key,
            )

            # 记录 fallback 选择
            event = None
            if recorder:
                event = await recorder.record_selection(
                    db,
                    provider_id=fallback_resolved.provider.id,
                    model_name=fallback_resolved.model,
                    agent_role_key=agent_key,
                    selection_mode="manual_with_fallback",
                    selection_score=fallback_resolved.selection_score,
                    selection_reason=f"fallback#{attempt_no} (主模型{primary_failure_type})",
                    project_id=project_id,
                    task_id=task_id,
                    chapter_id=chapter_id,
                    step_key=step_key,
                    agent_step_id=agent_step_id,
                    provider_name=fallback_resolved.provider.name,
                    request_id=request_id,
                    cache_hit=False,
                    event_type="fallback_triggered",
                    event_category="routing",
                    level="warning",
                )

            try:
                result = await self.client.chat(
                    base_url=fallback_resolved.provider.base_url,
                    api_key=fallback_resolved.provider.api_key,
                    request=request,
                    provider_extra=fallback_resolved.provider.extra or {},
                )
                if recorder and event:
                    await recorder.record_fallback_success(
                        db, event,
                        latency_ms=result.duration_ms,
                        input_tokens=result.input_tokens,
                        output_tokens=result.output_tokens,
                        cost_usd=result.cost_usd,
                        fallback_from_provider=primary_provider_name,
                        fallback_from_model=primary_model_name,
                        fallback_to_provider=fallback_resolved.provider.name,
                        fallback_to_model=fallback_resolved.model,
                    )
                if cache_enabled:
                    await self._store_cache_entry(
                        db,
                        request_id=request_id,
                        request_hash=request_hash,
                        request_payload=request_payload,
                        resolved=fallback_resolved,
                        agent_role_key=agent_key or fallback_agent_key,
                        step_key=step_key,
                        result=result,
                    )
                logger.info(
                    "fallback#%d 成功: %s/%s",
                    attempt_no, fallback_resolved.provider.name, fallback_resolved.model,
                )
                return fallback_resolved, result

            except Exception as exc2:
                failed_set.add((cand.provider_id, cand.model_name))
                if recorder and event:
                    failure_type2 = classify_llm_exception(exc2)
                    await recorder.record_failure(db, event, failure_type2, str(exc2)[:2000])
                # 更新熔断记录
                try:
                    from app.services.model_circuit_breaker import CircuitBreakerService
                    await CircuitBreakerService().record_failure(
                        db, cand.provider_id, cand.model_name, agent_key,
                        classify_llm_exception(exc2), str(exc2)[:2000],
                    )
                except Exception:
                    pass
                logger.warning(
                    "fallback#%d 失败 (%s/%s): %s",
                    attempt_no, fb_provider.name, cand.model_name, exc2,
                )
                # 继续下一个候选

        logger.warning("所有 fallback 候选均已耗尽")
        return None


_router_singleton: LLMRouter | None = None


def get_llm_router() -> LLMRouter:
    global _router_singleton
    if _router_singleton is None:
        from app.services.llm.client import get_llm_client
        _router_singleton = LLMRouter(get_llm_client())
    return _router_singleton
