"""ModelRouter — Worker 调用模型前的统一选择入口.

ALL agent LLM calls MUST go through ModelRouter.resolve().
Worker/Agent must NOT pick provider/model themselves.

Three modes:
- locked: strict provider+model, no fallback, no auto-switch
- manual_with_fallback: prefer user choice, fallback on failure
- auto: system picks best model by strategy + health

Every resolution writes a ModelRouteEvent audit record.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select

from app.core.database import session_scope
from app.models.agent_role import AgentModelBinding
from app.models.model_provider import ModelProvider
from app.models.model_health import ModelHealthSnapshot, ModelRouteEvent
from app.services.model_lock_guard import (
    LockedModelUnavailableError,
    ModelChoice,
    ModelLockGuard,
    NoAvailableModelError,
    PrimaryModelUnavailableError,
)
from app.services.model_strategy_engine import ModelStrategyEngine


class ModelRouter:
    """Unified model selection entry point."""

    def __init__(self):
        self._lock_guard = ModelLockGuard()
        self._strategy_engine = ModelStrategyEngine()

    async def resolve(
        self,
        agent_role_key: str,
        task_context: dict[str, Any] | None = None,
    ) -> ModelChoice:
        """Resolve which provider+model to use for an agent call.

        Args:
            agent_role_key: The agent's role key (e.g. "Planner", "Draft")
            task_context: Optional context (project_id, chapter_id, etc.)

        Returns:
            ModelChoice with provider_id, model_name, reason, etc.

        Raises:
            LockedModelUnavailableError: locked model is unavailable
            PrimaryModelUnavailableError: manual primary unavailable (no fallback)
            NoAvailableModelError: no usable model found
        """
        ctx = task_context or {}

        async with session_scope() as db:
            binding = await self._load_binding(db, agent_role_key)
            if binding is None:
                return await self._fallback_default(db, agent_role_key)

            mode = binding.binding_mode or self._map_selection_mode(binding.selection_mode)

            if mode == "locked":
                return await self._resolve_locked(db, binding, agent_role_key, ctx)
            elif mode == "manual_with_fallback":
                return await self._resolve_manual_with_fallback(db, binding, agent_role_key, ctx)
            else:
                return await self._resolve_auto(db, binding, agent_role_key, ctx)

    # ──── Private helpers ────

    async def _load_binding(self, db, agent_role_key: str) -> AgentModelBinding | None:
        from app.models.agent_role import AgentRole

        role = (await db.execute(
            select(AgentRole).where(AgentRole.key == agent_role_key)
        )).scalar_one_or_none()

        if role is None:
            # Try case-insensitive
            all_roles = (await db.execute(select(AgentRole))).scalars().all()
            role = next((r for r in all_roles if r.key.lower() == agent_role_key.lower()), None)

        if role is None:
            return None

        binding = (await db.execute(
            select(AgentModelBinding).where(
                AgentModelBinding.agent_role_id == role.id
            )
        )).scalar_one_or_none()

        return binding

    async def _resolve_locked(
        self, db, binding, agent_role_key: str, ctx: dict,
    ) -> ModelChoice:
        """Locked mode: only the specified provider+model."""
        locked_pid = binding.locked_provider_id
        locked_model = binding.locked_model_name

        if not locked_pid or not locked_model:
            raise LockedModelUnavailableError(
                f"Agent '{agent_role_key}' is locked but has no provider/model"
            )

        provider = (await db.execute(
            select(ModelProvider).where(ModelProvider.id == locked_pid)
        )).scalar_one_or_none()

        if not provider or not provider.enabled:
            await self._write_route_event(db, {
                "agent_role_key": agent_role_key,
                "binding_mode": "locked",
                "selected_provider_id": locked_pid,
                "selected_model_name": locked_model,
                "route_reason": "locked_by_user",
                "locked": True,
                "fallback_used": False,
                "error_message": f"Provider {locked_pid} not found or disabled",
            })
            raise LockedModelUnavailableError(
                f"Agent locked to provider id={locked_pid}, but provider is not available"
            )

        await self._write_route_event(db, {
            "agent_role_key": agent_role_key,
            "binding_mode": "locked",
            "selected_provider_id": locked_pid,
            "selected_model_name": locked_model,
            "route_reason": "locked_by_user",
            "locked": True,
            "fallback_used": False,
        })

        return ModelChoice(
            provider_id=locked_pid,
            model_name=locked_model or "",
            reason="locked_by_user",
            allow_fallback=False,
            auto_switch=False,
            locked=True,
        )

    async def _resolve_manual_with_fallback(
        self, db, binding, agent_role_key: str, ctx: dict,
    ) -> ModelChoice:
        """Manual mode: prefer binding.provider_id+model_name, fallback on failure."""
        primary_pid = binding.provider_id
        primary_model = binding.model_name

        if primary_pid and primary_model:
            if await self._is_usable(db, primary_pid, primary_model):
                await self._write_route_event(db, {
                    "agent_role_key": agent_role_key,
                    "binding_mode": "manual_with_fallback",
                    "strategy": binding.auto_strategy,
                    "selected_provider_id": primary_pid,
                    "selected_model_name": primary_model,
                    "route_reason": "manual_primary_ok",
                    "health_score": await self._get_health_score(db, primary_pid, primary_model),
                    "fallback_used": False,
                })
                return ModelChoice(
                    provider_id=primary_pid,
                    model_name=primary_model,
                    reason="manual_primary_ok",
                    allow_fallback=bool(binding.allow_fallback),
                    auto_switch=bool(binding.allow_auto_switch),
                    health_score=await self._get_health_score(db, primary_pid, primary_model),
                )

        # Try explicit fallback candidates
        fallbacks = binding.fallback_candidates_json or []
        if binding.allow_fallback and fallbacks:
            for fc in fallbacks:
                f_pid = fc.get("provider_id")
                f_model = fc.get("model_name")
                if f_pid and f_model and await self._is_usable(db, f_pid, f_model):
                    await self._write_route_event(db, {
                        "agent_role_key": agent_role_key,
                        "binding_mode": "manual_with_fallback",
                        "strategy": binding.auto_strategy,
                        "attempted_provider_id": primary_pid,
                        "attempted_model_name": primary_model,
                        "selected_provider_id": f_pid,
                        "selected_model_name": f_model,
                        "route_reason": "manual_primary_failed_fallback",
                        "fallback_used": True,
                        "fallback_reason": "Primary model unavailable, using fallback candidate",
                    })
                    return ModelChoice(
                        provider_id=f_pid,
                        model_name=f_model,
                        reason="manual_primary_failed_fallback",
                        allow_fallback=False,
                    )

        # If allow_auto_fallback, try auto resolution
        if binding.allow_auto_fallback:
            try:
                auto_choice = await self._resolve_auto(db, binding, agent_role_key, {"allow_mock": False})
                await self._write_route_event(db, {
                    "agent_role_key": agent_role_key,
                    "binding_mode": "manual_with_fallback",
                    "strategy": binding.auto_strategy,
                    "attempted_provider_id": primary_pid,
                    "attempted_model_name": primary_model,
                    "selected_provider_id": auto_choice.provider_id,
                    "selected_model_name": auto_choice.model_name,
                    "route_reason": "manual_primary_failed_fallback",
                    "fallback_used": True,
                    "fallback_reason": "Auto-fallback after primary model unavailable",
                })
                return auto_choice
            except NoAvailableModelError:
                pass

        raise PrimaryModelUnavailableError(
            f"Primary model for '{agent_role_key}' unavailable and no fallback succeeded"
        )

    async def _resolve_auto(
        self, db, binding, agent_role_key: str, ctx: dict,
    ) -> ModelChoice:
        """Auto mode: system picks best model by strategy + health."""
        strategy = binding.auto_strategy or self._strategy_engine.get_strategy_for_agent(agent_role_key)

        # Load candidate models
        candidates = await self._load_candidates(db, binding)

        # Filter by capability
        candidates = self._filter_capability(candidates, ctx)

        # Filter unhealthy
        candidates = self._filter_unhealthy(candidates)

        # Filter rate-limited/cooldown
        candidates = self._filter_rate_limited(candidates)

        # Filter mock in production
        if not ctx.get("allow_mock", True):
            candidates = [c for c in candidates if c.status != "mock"]

        if not candidates:
            raise NoAvailableModelError(
                f"No healthy model available for '{agent_role_key}'"
            )

        # Rank by strategy
        ranked = self._strategy_engine.rank(candidates, strategy)

        best = ranked[0]
        reason = f"auto_{strategy}"

        await self._write_route_event(db, {
            "agent_role_key": agent_role_key,
            "binding_mode": "auto",
            "strategy": strategy,
            "selected_provider_id": best.provider_id,
            "selected_model_name": best.model_name,
            "route_reason": reason,
            "health_score": best.health_score,
            "fallback_used": False,
        })

        return ModelChoice(
            provider_id=best.provider_id,
            model_name=best.model_name,
            reason=reason,
            allow_fallback=True,
            auto_switch=True,
            health_score=best.health_score,
        )

    async def _fallback_default(self, db, agent_role_key: str) -> ModelChoice:
        """Fallback to first enabled provider's default model."""
        providers = (await db.execute(
            select(ModelProvider)
            .where(ModelProvider.enabled == True)
            .order_by(ModelProvider.id.asc())
        )).scalars().all()

        for p in providers:
            model = p.default_model or (p.model_list and p.model_list[0])
            if model and p.base_url != "mock://local":
                return ModelChoice(
                    provider_id=p.id,
                    model_name=model,
                    reason="fallback_default",
                )

        # Ultimate fallback: stub
        stub = next((p for p in providers if p.base_url == "mock://local"), None)
        if stub:
            return ModelChoice(
                provider_id=stub.id,
                model_name=stub.default_model or "mock-fast",
                reason="fallback_default",
            )

        raise NoAvailableModelError("No provider configured")

    async def _load_candidates(
        self, db, binding,
    ) -> list[ModelHealthSnapshot]:
        """Load candidate ModelHealthSnapshot rows for auto resolution."""
        providers = (await db.execute(
            select(ModelProvider).where(ModelProvider.enabled == True)
        )).scalars().all()

        provider_ids = [p.id for p in providers]

        snapshots = (await db.execute(
            select(ModelHealthSnapshot).where(
                ModelHealthSnapshot.provider_id.in_(provider_ids)
            )
        )).scalars().all()

        if not snapshots:
            return []

        # Filter to text-capable
        snapshots = [s for s in snapshots if s.supports_text]

        return list(snapshots)

    def _filter_capability(
        self, candidates: list[ModelHealthSnapshot], ctx: dict,
    ) -> list[ModelHealthSnapshot]:
        """Filter models by required capabilities."""
        required = ctx.get("required_capabilities", [])
        if "json" in required or ctx.get("needs_json"):
            candidates = [c for c in candidates if c.supports_json]
        if "long_context" in required:
            candidates = [c for c in candidates if (c.context_window or 0) >= 32000]
        return candidates

    def _filter_unhealthy(
        self, candidates: list[ModelHealthSnapshot],
    ) -> list[ModelHealthSnapshot]:
        """Remove failing/disabled models."""
        return [c for c in candidates if c.status not in ("failing", "disabled")]

    def _filter_rate_limited(
        self, candidates: list[ModelHealthSnapshot],
    ) -> list[ModelHealthSnapshot]:
        """Remove rate-limited or cooldown models."""
        now = datetime.utcnow()
        return [
            c for c in candidates
            if (c.rate_limited_until is None or c.rate_limited_until < now)
            and (c.cooldown_until is None or c.cooldown_until < now)
        ]

    async def _is_usable(self, db, provider_id: int, model_name: str) -> bool:
        """Check if a specific model is usable."""
        provider = (await db.execute(
            select(ModelProvider).where(ModelProvider.id == provider_id)
        )).scalar_one_or_none()

        if not provider or not provider.enabled:
            return False

        model_list = provider.model_list or []
        if model_name not in model_list and model_name != provider.default_model:
            return False

        return True

    async def _get_health_score(
        self, db, provider_id: int, model_name: str,
    ) -> float | None:
        snap = (await db.execute(
            select(ModelHealthSnapshot).where(
                ModelHealthSnapshot.provider_id == provider_id,
                ModelHealthSnapshot.model_name == model_name,
            )
        )).scalar_one_or_none()
        return snap.health_score if snap else None

    async def _write_route_event(self, db, data: dict) -> None:
        """Write a ModelRouteEvent audit log."""
        try:
            event = ModelRouteEvent(
                task_id=data.get("task_id"),
                step_id=data.get("step_id"),
                agent_role_key=data["agent_role_key"],
                binding_mode=data["binding_mode"],
                strategy=data.get("strategy"),
                selected_provider_id=data.get("selected_provider_id"),
                selected_model_name=data.get("selected_model_name"),
                attempted_provider_id=data.get("attempted_provider_id"),
                attempted_model_name=data.get("attempted_model_name"),
                route_reason=data["route_reason"],
                locked=data.get("locked", False),
                fallback_used=data.get("fallback_used", False),
                fallback_reason=data.get("fallback_reason"),
                health_score=data.get("health_score"),
                error_code=data.get("error_code"),
                error_message=data.get("error_message"),
            )
            db.add(event)
            await db.flush()
        except Exception:
            pass  # Don't let audit failure block the call

    @staticmethod
    def _map_selection_mode(selection_mode: str) -> str:
        """Map old selection_mode to new binding_mode."""
        mapping = {
            "auto": "auto",
            "manual": "manual_with_fallback",
            "manual_with_fallback": "manual_with_fallback",
        }
        return mapping.get(selection_mode, "auto")
