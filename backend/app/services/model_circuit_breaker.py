"""P1-Model-Failover: 熔断器服务.

管理 Provider / Model 的熔断状态:
  - 401: 立即 open
  - 429: open 5~15 分钟
  - timeout 连续 2 次: open 3 分钟
  - 5xx 连续 3 次: open 5 分钟
  - empty_response 连续 2 次: open 2 分钟
  - half_open 探针: 到期后允许 1 个请求
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.model_call_event import ModelCallEvent
from app.models.model_provider import ModelProvider

logger = logging.getLogger(__name__)

# 熔断规则
CIRCUIT_RULES: dict[str, dict] = {
    "auth_error": {"duration": None, "consecutive": 1},
    # None = 直到用户手动 reset
    "rate_limited": {"duration": timedelta(minutes=10), "consecutive": 1},
    "timeout": {"duration": timedelta(minutes=3), "consecutive": 2},
    "server_error": {"duration": timedelta(minutes=5), "consecutive": 3},
    "connection_error": {"duration": timedelta(minutes=5), "consecutive": 3},
    "empty_response": {"duration": timedelta(minutes=2), "consecutive": 2},
    "model_not_found": {"duration": timedelta(hours=24), "consecutive": 1},
    "json_parse_failed": {"duration": None, "consecutive": 999},
    # json_parse_failed 不触发 Provider 熔断
    "budget_exhausted": {"duration": timedelta(hours=24), "consecutive": 1},
}


class CircuitBreakerService:
    """管理 Provider 熔断状态."""

    async def record_success(
        self,
        db: AsyncSession,
        provider_id: int,
        model_name: str | None,
        agent_role_key: str | None,
        latency_ms: int | None = None,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cost_usd: float = 0.0,
    ) -> None:
        """记录成功调用, 恢复熔断状态."""
        provider = await db.get(ModelProvider, provider_id)
        if provider is None:
            return

        provider.consecutive_failures = 0
        provider.consecutive_successes = (provider.consecutive_successes or 0) + 1
        provider.last_success_at = datetime.utcnow()

        # half_open → closed
        if provider.circuit_state == "half_open":
            provider.circuit_state = "closed"
            provider.circuit_open_until = None
            logger.info(f"Provider {provider.name} half_open → closed (探针成功)")
        elif provider.circuit_state == "open":
            # 仍然 open 但成功了 (不太可能), 清零
            provider.circuit_state = "closed"
            provider.circuit_open_until = None

        # 更新延迟
        if latency_ms is not None:
            if provider.avg_latency_ms is None:
                provider.avg_latency_ms = latency_ms
            else:
                provider.avg_latency_ms = int(provider.avg_latency_ms * 0.7 + latency_ms * 0.3)

        # 更新每日统计
        today = datetime.utcnow().strftime("%Y-%m-%d")
        if provider.last_reset_date != today:
            provider.daily_cost_usd = 0.0
            provider.daily_request_count = 0
            provider.daily_token_count = 0
            provider.last_reset_date = today

        provider.daily_request_count = (provider.daily_request_count or 0) + 1
        provider.daily_token_count = (provider.daily_token_count or 0) + input_tokens + output_tokens
        provider.daily_cost_usd = (provider.daily_cost_usd or 0.0) + cost_usd

        # 写 call event
        event = ModelCallEvent(
            provider_id=provider_id,
            model_name=model_name,
            agent_role_key=agent_role_key,
            status="success",
            latency_ms=latency_ms,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd,
        )
        db.add(event)

    async def record_failure(
        self,
        db: AsyncSession,
        provider_id: int,
        model_name: str | None,
        agent_role_key: str | None,
        failure_type: str,
        message: str | None = None,
        *,
        task_id: int | None = None,
        project_id: int | None = None,
    ) -> None:
        """记录失败调用, 可能触发熔断."""
        provider = await db.get(ModelProvider, provider_id)
        if provider is None:
            return

        provider.consecutive_failures = (provider.consecutive_failures or 0) + 1
        provider.consecutive_successes = 0
        provider.last_failure_type = failure_type
        provider.last_failure_message = (message or "")[:2000]
        provider.last_success_at = provider.last_success_at  # 保持不变

        # JSON 解析失败说明本次输出质量不可用，但通常不是 Provider 连通性坏了。
        # 立即降低健康分，避免继续高优先级命中同一组合；不打开 Provider 熔断。
        if failure_type == "json_parse_failed":
            provider.health_score = max(0.1, (provider.health_score or 0.75) - 0.1)
            logger.info(
                f"Provider {provider.name} JSON 解析失败, health_score 降至 {provider.health_score:.2f}"
            )

        # 检查是否需要熔断
        rule = CIRCUIT_RULES.get(failure_type, CIRCUIT_RULES.get("unknown", {}))
        required_consecutive = rule.get("consecutive", 3)
        duration = rule.get("duration")

        if failure_type != "json_parse_failed" and provider.consecutive_failures >= required_consecutive:
            if duration is not None:
                # 有限时熔断
                provider.circuit_state = "open"
                provider.circuit_open_until = datetime.utcnow() + duration
                logger.warning(
                    f"Provider {provider.name} 熔断 {duration}, 原因: {failure_type}"
                )
            elif failure_type == "auth_error":
                # 鉴权失败: 无限熔断, 需用户手动 reset
                provider.circuit_state = "open"
                provider.circuit_open_until = datetime.utcnow() + timedelta(days=365)
                logger.error(
                    f"Provider {provider.name} 鉴权失败, 熔断直到手动 reset"
                )
        # 写 call event
        event = ModelCallEvent(
            provider_id=provider_id,
            model_name=model_name,
            agent_role_key=agent_role_key,
            status="failed",
            failure_type=failure_type,
            failure_message=message,
            task_id=task_id,
            project_id=project_id,
        )
        db.add(event)

    async def should_skip_provider(
        self, db: AsyncSession, provider_id: int,
    ) -> tuple[bool, str | None]:
        """检查 Provider 是否应被跳过."""
        provider = await db.get(ModelProvider, provider_id)
        if provider is None:
            return True, "Provider 不存在"
        if not provider.enabled:
            return True, "Provider 已禁用"
        if provider.circuit_state == "open":
            if provider.circuit_open_until and provider.circuit_open_until > datetime.utcnow():
                return True, f"熔断中 (原因: {provider.last_failure_type})"
            # 过期了, 转 half_open
            provider.circuit_state = "half_open"
            return False, None  # 允许探针
        return False, None

    async def should_skip_model(
        self, db: AsyncSession, provider_id: int, model_name: str,
        agent_role_key: str | None,
    ) -> tuple[bool, str | None]:
        """检查特定模型是否应被跳过 (不影响整个 Provider)."""
        skip, reason = await self.should_skip_provider(db, provider_id)
        if skip:
            return skip, reason

        # 检查最近是否有 model_not_found
        recent = (await db.execute(
            select(ModelCallEvent).where(
                and_(
                    ModelCallEvent.provider_id == provider_id,
                    ModelCallEvent.model_name == model_name,
                    ModelCallEvent.failure_type == "model_not_found",
                )
            ).order_by(ModelCallEvent.created_at.desc()).limit(1)
        )).scalar_one_or_none()

        if recent:
            return True, f"模型 {model_name} 不可用 (model_not_found)"

        return False, None

    async def reset_circuit(
        self, db: AsyncSession, provider_id: int,
    ) -> ModelProvider:
        """手动重置熔断状态."""
        provider = await db.get(ModelProvider, provider_id)
        if provider is None:
            raise ValueError(f"Provider {provider_id} 不存在")
        provider.circuit_state = "closed"
        provider.circuit_open_until = None
        provider.consecutive_failures = 0
        provider.last_failure_type = None
        provider.last_failure_message = None
        return provider

    async def check_half_open(self, db: AsyncSession) -> int:
        """检查所有 open 且到期的 Provider, 转为 half_open.
        返回转换数量."""
        now = datetime.utcnow()
        providers = (await db.execute(
            select(ModelProvider).where(
                and_(
                    ModelProvider.circuit_state == "open",
                    ModelProvider.circuit_open_until != None,  # noqa: E711
                    ModelProvider.circuit_open_until <= now,
                )
            )
        )).scalars().all()

        count = 0
        for p in providers:
            p.circuit_state = "half_open"
            count += 1
            logger.info(f"Provider {p.name} half_open (熔断到期)")

        return count
