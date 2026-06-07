"""P1-Model-Failover: 模型调用记录器.

每次模型调用前记录 selection, 成功/失败后写 event,
聚合更新 ModelRuntimeStat, 更新 Provider 健康分.
"""
from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.model_call_event import ModelCallEvent
from app.models.model_provider import ModelProvider
from app.models.model_runtime import ModelRuntimeStat

logger = logging.getLogger(__name__)

# failure_type → event_type 映射
_FAILURE_TYPE_TO_EVENT_TYPE: dict[str, str] = {
    "timeout": "request_timeout",
    "json_parse_failed": "json_parse_failed",
    "empty_response": "empty_output",
}

# failure_type → level 映射
_FAILURE_TYPE_TO_LEVEL: dict[str, str] = {
    "auth_error": "critical",
}


class ModelCallRecorder:
    """记录每次模型调用的选择和结果."""

    async def record_selection(
        self,
        db: AsyncSession,
        *,
        provider_id: int | None,
        model_name: str | None,
        agent_role_key: str | None,
        selection_mode: str | None = None,
        selection_score: float | None = None,
        selection_reason: str | None = None,
        project_id: int | None = None,
        task_id: int | None = None,
        agent_step_id: int | None = None,
        chapter_id: int | None = None,
        step_key: str | None = None,
        provider_name: str | None = None,
        request_id: str | None = None,
        cache_hit: bool | None = None,
        event_type: str = "request_started",
        event_category: str = "request",
        level: str = "info",
        summary: str | None = None,
    ) -> ModelCallEvent:
        """记录模型选择 (调用前)."""
        # 自动生成 summary
        if summary is None and agent_role_key and model_name:
            parts = [agent_role_key, "→", f"{provider_name or '?'}/{model_name}"]
            if selection_mode:
                parts.append(f"· {selection_mode}")
            if selection_score is not None:
                parts.append(f"· score={selection_score:.2f}")
            summary = " ".join(parts)

        event = ModelCallEvent(
            provider_id=provider_id,
            model_name=model_name,
            agent_role_key=agent_role_key,
            project_id=project_id,
            task_id=task_id,
            agent_step_id=agent_step_id,
            chapter_id=chapter_id,
            step_key=step_key,
            provider_name=provider_name,
            request_id=request_id,
            cache_hit=cache_hit,
            selection_mode=selection_mode,
            selection_score=selection_score,
            selection_reason=selection_reason,
            status="pending",  # 待完成
            event_type=event_type,
            event_category=event_category,
            level=level,
            summary=summary,
        )
        db.add(event)
        await db.flush()
        return event

    async def record_success(
        self,
        db: AsyncSession,
        event: ModelCallEvent,
        latency_ms: int | None = None,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cost_usd: float = 0.0,
    ) -> None:
        """标记调用成功并更新统计."""
        event.status = "success"
        event.latency_ms = latency_ms
        event.input_tokens = input_tokens
        event.output_tokens = output_tokens
        event.cost_usd = cost_usd
        event.event_type = "request_succeeded"
        event.event_category = "request"
        event.level = "success"

        # 自动生成 summary
        parts = [event.agent_role_key or "?", "→",
                 f"{event.provider_name or '?'}/{event.model_name or '?'}", "· 成功"]
        if latency_ms is not None:
            parts.append(f"· {latency_ms}ms")
        if input_tokens or output_tokens:
            parts.append(f"· {input_tokens + output_tokens} tokens")
        if cost_usd > 0:
            parts.append(f"· ${cost_usd:.4f}")
        event.summary = " ".join(parts)

        # 更新 runtime stat
        await self._update_runtime_stat(
            db, event.provider_id, event.model_name,
            event.agent_role_key, "rolling_24h",
            success=True, latency_ms=latency_ms,
            input_tokens=input_tokens, output_tokens=output_tokens,
            cost_usd=cost_usd,
        )

        # 更新 Provider 健康分
        if event.provider_id:
            provider = await db.get(ModelProvider, event.provider_id)
            if provider:
                provider.consecutive_failures = 0
                provider.consecutive_successes = (provider.consecutive_successes or 0) + 1
                provider.last_success_at = datetime.utcnow()
                if provider.circuit_state == "half_open":
                    provider.circuit_state = "closed"
                    provider.circuit_open_until = None
                if latency_ms is not None:
                    if provider.avg_latency_ms is None:
                        provider.avg_latency_ms = latency_ms
                    else:
                        provider.avg_latency_ms = int(
                            provider.avg_latency_ms * 0.7 + latency_ms * 0.3
                        )

    async def record_cache_hit(
        self,
        db: AsyncSession,
        event: ModelCallEvent,
        *,
        input_tokens: int = 0,
        output_tokens: int = 0,
    ) -> None:
        """Mark an event as served from exact cache.

        Cache hits are intentionally excluded from provider runtime
        success/cost stats because no upstream model call happened.
        """
        event.status = "success"
        event.cache_hit = True
        event.latency_ms = 0
        event.input_tokens = 0
        event.output_tokens = 0
        event.cost_usd = 0.0
        event.event_type = "cache_hit"
        event.event_category = "cache"
        event.level = "success"
        token_hint = ""
        if input_tokens or output_tokens:
            token_hint = f" | cached_tokens={input_tokens + output_tokens}"
        event.summary = (
            f"{event.agent_role_key or '?'} -> "
            f"{event.provider_name or '?'}/{event.model_name or '?'} | cache hit"
            f"{token_hint}"
        )

    async def record_failure(
        self,
        db: AsyncSession,
        event: ModelCallEvent,
        failure_type: str,
        failure_message: str | None = None,
    ) -> None:
        """标记调用失败并更新统计."""
        event.status = "failed"
        event.failure_type = failure_type
        event.failure_message = failure_message

        # 映射 event_type
        event.event_type = _FAILURE_TYPE_TO_EVENT_TYPE.get(failure_type, "request_failed")
        event.event_category = "request"
        event.level = _FAILURE_TYPE_TO_LEVEL.get(failure_type, "error")
        event.error_code = failure_type

        # 自动生成 summary
        parts = [event.agent_role_key or "?", "→",
                 f"{event.provider_name or '?'}/{event.model_name or '?'}"]
        # 友好化 failure_type
        ft_display = {
            "json_parse_failed": "JSON解析失败",
            "empty_response": "空输出",
            "timeout": "超时",
            "auth_error": "鉴权失败",
            "rate_limited": "限流",
        }.get(failure_type, failure_type)
        parts.append(f"· {ft_display}")
        if failure_message:
            parts.append(f"· {failure_message[:80]}")
        event.summary = " ".join(parts)

        # 更新 runtime stat
        stat_update = {"success": False, failure_type: True}
        await self._update_runtime_stat(
            db, event.provider_id, event.model_name,
            event.agent_role_key, "rolling_24h",
            success=False, failure_type=failure_type,
        )

    async def record_fallback_success(
        self,
        db: AsyncSession,
        event: ModelCallEvent,
        latency_ms: int | None = None,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cost_usd: float = 0.0,
        *,
        fallback_from_provider: str | None = None,
        fallback_from_model: str | None = None,
        fallback_to_provider: str | None = None,
        fallback_to_model: str | None = None,
    ) -> None:
        """记录 fallback 成功."""
        event.status = "fallback_success"
        event.latency_ms = latency_ms
        event.input_tokens = input_tokens
        event.output_tokens = output_tokens
        event.cost_usd = cost_usd
        event.event_type = "fallback_succeeded"
        event.event_category = "routing"
        event.level = "warning"
        event.fallback_from_provider = fallback_from_provider
        event.fallback_from_model = fallback_from_model
        event.fallback_to_provider = fallback_to_provider
        event.fallback_to_model = fallback_to_model

        # 自动生成 summary
        parts = [event.agent_role_key or "?"]
        if fallback_from_provider and fallback_from_model:
            parts.append(f"{fallback_from_provider}/{fallback_from_model}")
        parts.append("→ fallback →")
        if fallback_to_provider and fallback_to_model:
            parts.append(f"{fallback_to_provider}/{fallback_to_model}")
        parts.append("· 成功")
        if latency_ms is not None:
            parts.append(f"· {latency_ms}ms")
        event.summary = " ".join(parts)

        # 更新 runtime stat
        await self._update_runtime_stat(
            db, event.provider_id, event.model_name,
            event.agent_role_key, "rolling_24h",
            success=True, latency_ms=latency_ms,
            input_tokens=input_tokens, output_tokens=output_tokens,
            cost_usd=cost_usd,
        )

    # ── 内部方法 ──

    async def _update_runtime_stat(
        self,
        db: AsyncSession,
        provider_id: int | None,
        model_name: str | None,
        agent_role_key: str | None,
        window: str,
        *,
        success: bool,
        latency_ms: int | None = None,
        failure_type: str | None = None,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cost_usd: float = 0.0,
    ) -> None:
        """更新或创建 ModelRuntimeStat 行."""
        if provider_id is None or model_name is None:
            return

        stat = (await db.execute(
            select(ModelRuntimeStat).where(
                and_(
                    ModelRuntimeStat.provider_id == provider_id,
                    ModelRuntimeStat.model_name == model_name,
                    ModelRuntimeStat.agent_role_key == agent_role_key,
                    ModelRuntimeStat.window == window,
                )
            )
        )).scalar_one_or_none()

        if stat is None:
            stat = ModelRuntimeStat(
                provider_id=provider_id,
                model_name=model_name,
                agent_role_key=agent_role_key,
                window=window,
                total_calls=0,
                success_calls=0,
                failed_calls=0,
                json_parse_failures=0,
                empty_response_failures=0,
                timeout_failures=0,
                auth_failures=0,
                rate_limit_failures=0,
            )
            db.add(stat)
            await db.flush()

        stat.total_calls = (stat.total_calls or 0) + 1
        if success:
            stat.success_calls = (stat.success_calls or 0) + 1
        else:
            stat.failed_calls = (stat.failed_calls or 0) + 1

        # 特定失败类型计数
        if failure_type == "json_parse_failed":
            stat.json_parse_failures = (stat.json_parse_failures or 0) + 1
        elif failure_type == "empty_response":
            stat.empty_response_failures = (stat.empty_response_failures or 0) + 1
        elif failure_type == "timeout":
            stat.timeout_failures = (stat.timeout_failures or 0) + 1
        elif failure_type == "auth_error":
            stat.auth_failures = (stat.auth_failures or 0) + 1
        elif failure_type == "rate_limited":
            stat.rate_limit_failures = (stat.rate_limit_failures or 0) + 1

        # 延迟 EMA
        if latency_ms is not None:
            if stat.avg_latency_ms is None:
                stat.avg_latency_ms = latency_ms
            else:
                stat.avg_latency_ms = int(stat.avg_latency_ms * 0.8 + latency_ms * 0.2)

        # Token/Cost
        stat.input_tokens = (stat.input_tokens or 0) + input_tokens
        stat.output_tokens = (stat.output_tokens or 0) + output_tokens
        stat.cost_usd = (stat.cost_usd or 0.0) + cost_usd

        # 成功率
        if stat.total_calls > 0:
            stat.quality_score = stat.success_calls / stat.total_calls
