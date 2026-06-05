"""ModelHealthMonitor — 定时监测 Provider/Model 状态.

Responsibilities:
- Probe models every 5-30 minutes
- Update model_health_snapshots table
- Trigger on save, test, and call result events
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from app.core.database import session_scope
from app.models.model_provider import ModelProvider
from app.models.model_health import ModelHealthSnapshot
from sqlalchemy import select


class ModelHealthMonitor:
    """Periodic model health checker."""

    async def probe_all_providers(self) -> dict[str, Any]:
        """Probe all enabled providers and their models in batch.

        Returns summary: {provider_count, model_count, healthy, degraded, failing}
        """
        summary = {"provider_count": 0, "model_count": 0, "healthy": 0, "degraded": 0, "failing": 0}

        async with session_scope() as db:
            providers = (await db.execute(
                select(ModelProvider).where(ModelProvider.enabled == True)
            )).scalars().all()

            summary["provider_count"] = len(providers)

        from app.services.model_probe_service import ModelProbeService
        probe_svc = ModelProbeService()

        for provider in providers:
            if not provider.model_list:
                continue

            for model_name in provider.model_list:
                summary["model_count"] += 1
                result = await probe_svc.probe_model(
                    provider_id=provider.id,
                    model_name=model_name,
                    base_url=provider.base_url,
                    api_key=provider.api_key or "",
                )

                await self._update_snapshot(db_arg=None, provider_id=provider.id, result=result)

                if result.status == "healthy":
                    summary["healthy"] += 1
                elif result.status == "degraded" or result.status == "rate_limited":
                    summary["degraded"] += 1
                else:
                    summary["failing"] += 1

        return summary

    async def probe_provider_models(self, provider_id: int) -> list[dict]:
        """Probe all models on a single provider."""
        from app.services.model_probe_service import ModelProbeService
        probe_svc = ModelProbeService()

        async with session_scope() as db:
            provider = (await db.execute(
                select(ModelProvider).where(ModelProvider.id == provider_id)
            )).scalar_one_or_none()

            if not provider or not provider.model_list:
                return []

        results = []
        for model_name in (provider.model_list or []):
            result = await probe_svc.probe_model(
                provider_id=provider.id,
                model_name=model_name,
                base_url=provider.base_url,
                api_key=provider.api_key or "",
            )
            await self._update_snapshot(db_arg=None, provider_id=provider.id, result=result)
            results.append({
                "model_name": model_name,
                "status": result.status,
                "latency_ms": result.latency_ms,
                "has_json": result.has_json,
                "error_message": result.error_message,
                "health_score": result.health_score,
            })

        return results

    async def record_call_result(
        self,
        provider_id: int,
        model_name: str,
        success: bool,
        latency_ms: int,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> None:
        """Record a call result and update health snapshot."""
        from app.services.model_probe_service import ModelProbeResult

        result = ModelProbeResult(
            ok=success,
            model_name=model_name,
            provider_id=provider_id,
            status="healthy" if success else "failing",
            latency_ms=latency_ms,
            error_code=error_code,
            error_message=error_message,
            health_score=1.0 if success else 0.0,
        )
        await self._update_snapshot(db_arg=None, provider_id=provider_id, result=result)

    async def _update_snapshot(
        self,
        db_arg,
        provider_id: int,
        result: "ModelProbeResult",
    ) -> ModelHealthSnapshot:
        """Update or create a ModelHealthSnapshot for a provider+model pair."""
        from app.services.model_probe_service import ModelProbeResult

        async with session_scope() as db:
            row = (await db.execute(
                select(ModelHealthSnapshot).where(
                    ModelHealthSnapshot.provider_id == provider_id,
                    ModelHealthSnapshot.model_name == result.model_name,
                )
            )).scalar_one_or_none()

            now = datetime.utcnow()

            if row is None:
                row = ModelHealthSnapshot(
                    provider_id=provider_id,
                    model_name=result.model_name,
                    status=result.status,
                    health_score=result.health_score,
                    avg_latency_ms=result.latency_ms,
                    supports_json=result.has_json,
                    supports_text=result.has_text,
                    probe_count=1,
                    consecutive_failures=0 if result.ok else 1,
                )
                if result.ok:
                    row.last_success_at = now
                    row.success_rate = 1.0
                else:
                    row.last_failure_at = now
                    row.last_error_code = result.error_code
                    row.last_error_message = result.error_message
                    row.error_rate = 1.0
                db.add(row)
            else:
                row.probe_count += 1
                row.health_score = self._compute_health_score(
                    row=row, new_ok=result.ok, new_latency=result.latency_ms,
                )
                row.avg_latency_ms = int(
                    (row.avg_latency_ms * (row.probe_count - 1) + result.latency_ms)
                    / row.probe_count
                ) if row.probe_count > 0 else result.latency_ms

                if result.ok:
                    row.last_success_at = now
                    row.consecutive_failures = 0
                    row.status = "healthy"
                else:
                    row.last_failure_at = now
                    row.last_error_code = result.error_code
                    row.last_error_message = result.error_message
                    row.consecutive_failures += 1
                    if row.consecutive_failures >= 5:
                        row.status = "failing"
                        row.cooldown_until = now + timedelta(minutes=10)
                    elif row.consecutive_failures >= 3:
                        row.status = "failing"
                    elif result.status == "rate_limited":
                        row.status = "rate_limited"
                    else:
                        row.status = "degraded"

                # Update success/error rates (EMA)
                alpha = 0.2
                row.success_rate = row.success_rate * (1 - alpha) + (1.0 if result.ok else 0.0) * alpha
                row.error_rate = 1.0 - row.success_rate

            row.updated_at = now
            await db.flush()
            return row

    @staticmethod
    def _compute_health_score(
        row: ModelHealthSnapshot,
        new_ok: bool,
        new_latency: int,
    ) -> float:
        """Compute health score as weighted average of factors.

        success_rate * 0.35 + latency_score * 0.20 + capability_score * 0.15
        + cost_score * 0.10 + stability_score * 0.15 + recent_success * 0.05
        """
        success_rate = row.success_rate or 0.5
        if row.probe_count > 0:
            alpha = 0.2
            success_rate = success_rate * (1 - alpha) + (1.0 if new_ok else 0.0) * alpha

        # Latency: 0-2000ms = 1.0, 2000-5000 = 0.7, 5000-10000 = 0.4, >10000 = 0.1
        avg_lat = row.avg_latency_ms or new_latency
        if avg_lat <= 2000:
            latency_score = 1.0
        elif avg_lat <= 5000:
            latency_score = 0.7
        elif avg_lat <= 10000:
            latency_score = 0.4
        else:
            latency_score = 0.1

        # Capability: supports_json gives bonus
        capability_score = 0.7 if row.supports_json else 0.3

        # Cost: TODO — use real pricing, placeholder for now
        cost_score = 0.5

        # Stability: based on consecutive_failures
        cf = row.consecutive_failures or 0
        if cf == 0:
            stability_score = 1.0
        elif cf <= 2:
            stability_score = 0.7
        elif cf <= 5:
            stability_score = 0.3
        else:
            stability_score = 0.0

        # Recent success bonus: if new call succeeded
        recent_bonus = 1.0 if new_ok else 0.0

        return (
            success_rate * 0.35
            + latency_score * 0.20
            + capability_score * 0.15
            + cost_score * 0.10
            + stability_score * 0.15
            + recent_bonus * 0.05
        )
