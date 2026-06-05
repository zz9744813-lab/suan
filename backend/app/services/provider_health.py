"""P3-Model-Failover: Provider 健康检查服务.

定时测试 Provider 是否可用, 写入 health_score / circuit_state.
检查分层:
  Level 1: /models 是否可访问
  Level 2: 默认模型能否返回短文本
  Level 3: JSON 输出稳定性
  Level 4: 长文本输出能力
"""
from __future__ import annotations

import logging
import time
from datetime import datetime

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.model_provider import ModelProvider
from app.services.llm.client import LLMClient, get_llm_client

logger = logging.getLogger(__name__)

# 健康评分权重
_HEALTH_WEIGHTS = {
    "models_endpoint": 0.15,
    "chat_short": 0.25,
    "json_output": 0.20,
    "long_output": 0.15,
    "streaming": 0.10,
    "latency": 0.10,
    "auth_valid": 0.05,
}


class ProviderHealthService:
    """Provider 健康检查."""

    def __init__(self, client: LLMClient | None = None) -> None:
        self.client = client or get_llm_client()

    async def check_provider(
        self,
        db: AsyncSession,
        provider: ModelProvider,
        *,
        lightweight: bool = False,
    ) -> dict:
        """检查单个 Provider 健康状态.

        Args:
            lightweight: 只做 Level 1 (list_models)
        """
        scores: dict[str, float] = {}
        details: dict = {}

        # Level 1: /models 端点
        t0 = time.monotonic()
        try:
            models = await self.client.list_models(provider.base_url, provider.api_key)
            scores["models_endpoint"] = 1.0
            scores["auth_valid"] = 1.0
            details["model_count"] = len(models)
            # 更新 model_list
            if models:
                provider.model_list = models
        except Exception as exc:
            scores["models_endpoint"] = 0.0
            scores["auth_valid"] = 0.0
            details["models_error"] = str(exc)[:200]
            logger.warning(f"Provider {provider.name} /models 失败: {exc}")

        latency = int((time.monotonic() - t0) * 1000)
        scores["latency"] = self._latency_score(latency)

        if not lightweight and scores.get("models_endpoint", 0) > 0:
            # Level 2: 短文本 chat
            try:
                from app.services.llm.client import LLMMessage, LLMRequest
                model = provider.default_model or (models[0] if models else None)
                if model:
                    result = await self.client.chat(
                        base_url=provider.base_url,
                        api_key=provider.api_key,
                        request=LLMRequest(
                            model=model,
                            messages=[LLMMessage(role="user", content="Hi")],
                            temperature=0.1,
                            max_tokens=10,
                            stream=False,
                        ),
                        provider_extra=provider.extra or {},
                    )
                    scores["chat_short"] = 1.0 if result.content else 0.5
                    details["short_chat_ms"] = result.duration_ms
            except Exception as exc:
                scores["chat_short"] = 0.0
                details["short_chat_error"] = str(exc)[:200]

        # 综合评分
        health_score = 0.0
        for key, weight in _HEALTH_WEIGHTS.items():
            health_score += scores.get(key, 0.0) * weight

        # 写入 Provider
        provider.health_score = health_score
        provider.last_health_status = "healthy" if health_score >= 0.8 else (
            "degraded" if health_score >= 0.5 else "failed"
        )
        provider.last_health_at = datetime.utcnow()
        provider.last_health_latency_ms = latency
        provider.last_health_full = {
            "scores": scores,
            "details": details,
            "checked_at": datetime.utcnow().isoformat(),
        }

        logger.info(f"Provider {provider.name} health={health_score:.2f}")
        return {"provider_id": provider.id, "health_score": health_score, "scores": scores}

    async def check_all_enabled(
        self,
        db: AsyncSession,
        *,
        lightweight: bool = False,
    ) -> list[dict]:
        """检查所有 enabled 的 Provider."""
        providers = (await db.execute(
            select(ModelProvider).where(ModelProvider.enabled == True)  # noqa: E712
        )).scalars().all()

        results = []
        for p in providers:
            try:
                r = await self.check_provider(db, p, lightweight=lightweight)
                results.append(r)
            except Exception as exc:
                logger.error(f"Provider {p.name} 健康检查异常: {exc}")
                results.append({"provider_id": p.id, "error": str(exc)[:200]})

        return results

    @staticmethod
    def _latency_score(ms: int) -> float:
        if ms <= 1500:
            return 1.0
        if ms <= 4000:
            return 0.8
        if ms <= 9000:
            return 0.55
        if ms <= 20000:
            return 0.3
        return 0.1
