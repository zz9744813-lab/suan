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
    ) -> ModelCallEvent:
        """记录模型选择 (调用前)."""
        event = ModelCallEvent(
            provider_id=provider_id,
            model_name=model_name,
            agent_role_key=agent_role_key,
            project_id=project_id,
            task_id=task_id,
            selection_mode=selection_mode,
            selection_score=selection_score,
            selection_reason=selection_reason,
            status="pending",  # 待完成
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
    ) -> None:
        """记录 fallback 成功."""
        event.status = "fallback_success"
        event.latency_ms = latency_ms
        event.input_tokens = input_tokens
        event.output_tokens = output_tokens
        event.cost_usd = cost_usd

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
