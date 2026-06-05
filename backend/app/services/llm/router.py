"""LLMRouter: map agent role -> provider/model using DB-backed assignments.

P2-Model-Failover: resolve() 优先走新 AgentModelBinding + ModelSelector,
兼容旧 ModelRoleAssignment. chat() 增加 fallback 重试链.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
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

logger = logging.getLogger(__name__)

# 单次 Agent 调用内最多 fallback 次数
MAX_FALLBACK_ATTEMPTS = 2


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

    async def resolve(self, db: AsyncSession, role: str) -> ResolvedCall:
        """解析角色 → 模型. 优先走 ModelSelector, 兼容旧 ModelRoleAssignment."""
        # ── P2: 优先走新 AgentModelBinding + ModelSelector ──
        agent_key = LEGACY_ROLE_TO_AGENT_KEY.get(role)
        if agent_key:
            try:
                from app.services.model_selector import get_model_selector
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
        if result and result.provider and result.provider.enabled:
            return ResolvedCall(
                provider=result.provider,
                model=result.model,
                temperature=result.temperature,
                max_tokens=result.max_tokens,
                selection_mode="manual",
                selection_reason=f"旧绑定: {result.provider.name}/{result.model}",
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

        # ── 记录选择事件 ──
        from app.services.model_call_recorder import ModelCallRecorder
        recorder = ModelCallRecorder()
        event = await recorder.record_selection(
            db,
            provider_id=resolved.provider.id,
            model_name=resolved.model,
            agent_role_key=LEGACY_ROLE_TO_AGENT_KEY.get(role),
            selection_mode=resolved.selection_mode,
            selection_score=resolved.selection_score,
            selection_reason=resolved.selection_reason,
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
            agent_key = LEGACY_ROLE_TO_AGENT_KEY.get(role)
            if agent_key and resolved.selection_mode != "manual":
                fallback_result = await self._try_fallback(
                    db, role, agent_key, messages,
                    temperature=temperature, max_tokens=max_tokens,
                    response_format=response_format, extra=extra,
                    stream=stream, recorder=recorder,
                    primary_failure_type=failure_type,
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
    ) -> tuple[ResolvedCall, LLMCallResult] | None:
        """尝试 fallback 到下一个候选模型."""
        from app.services.model_selector import get_model_selector

        try:
            selected = await get_model_selector().select_for_agent(
                db, agent_role_key=agent_key, legacy_role=role,
                force_fallback=True,
            )
        except Exception:
            return None

        # 跳过跟主模型相同的 provider+model
        # (已在 ModelSelector 的 candidate 评分中降权)

        fallback_resolved = ResolvedCall(
            provider=selected.provider,
            model=selected.model_name,
            temperature=selected.temperature,
            max_tokens=selected.max_tokens,
            extra_body=selected.extra_body,
            selection_mode="manual_with_fallback",
            selection_score=selected.selection_score,
            selection_reason=f"fallback: {selected.selection_reason}",
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

        # 记录 fallback 选择
        if recorder:
            event = await recorder.record_selection(
                db,
                provider_id=fallback_resolved.provider.id,
                model_name=fallback_resolved.model,
                agent_role_key=agent_key,
                selection_mode="manual_with_fallback",
                selection_score=fallback_resolved.selection_score,
                selection_reason=f"fallback (主模型{primary_failure_type})",
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
                )
            logger.info(
                f"fallback 成功: {fallback_resolved.provider.name}/{fallback_resolved.model}"
            )
            return fallback_resolved, result
        except Exception as exc2:
            if recorder and event:
                failure_type2 = classify_llm_exception(exc2)
                await recorder.record_failure(db, event, failure_type2, str(exc2)[:2000])
            logger.warning(f"fallback 也失败: {exc2}")
            return None


_router_singleton: LLMRouter | None = None


def get_llm_router() -> LLMRouter:
    global _router_singleton
    if _router_singleton is None:
        from app.services.llm.client import get_llm_client
        _router_singleton = LLMRouter(get_llm_client())
    return _router_singleton
