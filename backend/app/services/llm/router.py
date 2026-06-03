"""LLMRouter: map agent role -> provider/model using DB-backed assignments.

If no assignment exists for a role, the router falls back to the first enabled
provider and its default model. This keeps the system usable out of the box
even before the user configures role bindings.
"""
from __future__ import annotations

from dataclasses import dataclass
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
    LLMResponseError,
)


@dataclass
class ResolvedCall:
    provider: ModelProvider
    model: str
    temperature: float
    max_tokens: int


class LLMRouter:
    def __init__(self, client: LLMClient) -> None:
        self.client = client

    async def resolve(self, db: AsyncSession, role: str) -> ResolvedCall:
        stmt = (
            select(ModelRoleAssignment)
            .options(selectinload(ModelRoleAssignment.provider))
            .where(ModelRoleAssignment.role == role)
        )
        # P15 / P0-STUDY-1 fix: use ``.scalars().first()`` (not
        # ``scalar_one_or_none()``) so multiple role-assignment rows
        # for the same role don't blow up the call. In practice the
        # UI only shows one row per role, but the DB doesn't enforce
        # that constraint and an older seed script or a manual
        # import may leave duplicates. Pick the lowest-id row — the
        # most recent assignment wins visually because the UI sorts
        # by id desc, so taking the smallest id gives us the
        # original "first" binding.
        result = (
            await db.execute(stmt.order_by(ModelRoleAssignment.id.asc()))
        ).scalars().first()
        if result and result.provider and result.provider.enabled:
            return ResolvedCall(
                provider=result.provider,
                model=result.model,
                temperature=result.temperature,
                max_tokens=result.max_tokens,
            )
        # fallback: first enabled provider with a default model
        # Same fix: ``.scalars().first()`` to avoid MultipleResultsFound
        # when the user has more than one provider enabled, AND to
        # return a model instance (not a Row tuple) so attribute
        # access works on ``first.default_model`` below. ORDER BY id
        # keeps the pick stable across calls.
        first = (
            await db.execute(
                select(ModelProvider)
                .where(ModelProvider.enabled.is_(True))
                .order_by(ModelProvider.id.asc())
                .limit(1)
            )
        ).scalars().first()
        if first is None:
            raise bad_request(
                "尚未配置任何已启用的模型 Provider",
                suggestion="请先在「模型配置」页添加 Provider 并启用。",
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
        # R15: when True (default), the LLM client opens an SSE stream
        # so the first token reaches the caller in 1-5s. Identical
        # cost / output shape as non-streaming — only the delivery
        # mechanism differs. The picker still runs at the end so the
        # returned content is unchanged.
        stream: bool = True,
    ) -> tuple[ResolvedCall, LLMCallResult]:
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
        try:
            result = await self.client.chat(
                base_url=resolved.provider.base_url,
                api_key=resolved.provider.api_key,
                request=request,
                provider_extra=resolved.provider.extra or {},
            )
        except LLMAuthError as exc:
            raise model_connection_error(
                f"模型鉴权失败（{resolved.provider.name}）: {exc}",
                suggestion="请检查 API Key 是否有效或已过期。",
            ) from exc
        except LLMConnectionError as exc:
            raise model_connection_error(
                f"无法连接模型（{resolved.provider.name}）: {exc}",
                suggestion="请检查 Base URL 是否可访问，或网络是否通畅。",
            ) from exc
        except LLMResponseError as exc:
            raise model_connection_error(
                f"模型返回异常（{resolved.provider.name}）: {exc}",
                suggestion="请稍后重试，或更换模型。",
            ) from exc
        except LLMError as exc:  # pragma: no cover
            raise model_connection_error(f"模型调用失败: {exc}") from exc
        return resolved, result


_router_singleton: LLMRouter | None = None


def get_llm_router() -> LLMRouter:
    global _router_singleton
    if _router_singleton is None:
        from app.services.llm.client import get_llm_client
        _router_singleton = LLMRouter(get_llm_client())
    return _router_singleton
