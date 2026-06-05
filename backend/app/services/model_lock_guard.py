"""ModelLockGuard — 防止 locked Agent 被自动切换.

Rules:
- binding_mode == "locked" → 只允许 locked_provider_id + locked_model_name
- locked 模式下 fallback / auto_switch 强制 false
- 模型不存在/provider 禁用 → 任务失败/暂停
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class ModelChoice:
    """Result of model routing decision."""
    provider_id: int
    model_name: str
    reason: str
    allow_fallback: bool = True
    auto_switch: bool = True
    locked: bool = False
    health_score: float | None = None


class LockedModelUnavailableError(Exception):
    """Raised when a locked model is unavailable — no fallback allowed."""
    def __init__(self, msg: str):
        super().__init__(msg)


class PrimaryModelUnavailableError(Exception):
    """Raised when manual_with_fallback primary model is unavailable."""
    def __init__(self, msg: str):
        super().__init__(msg)


class NoAvailableModelError(Exception):
    """Raised when no model is available across all providers."""
    def __init__(self, msg: str = "No available model"):
        super().__init__(msg)


class ModelLockGuard:
    """Enforce lock rules for locked agents."""

    async def validate_locked_binding(self, binding: object) -> None:
        """Raise LockedModelUnavailableError if the locked model is unusable."""
        from sqlalchemy import select
        from app.models.model_provider import ModelProvider
        from app.core.database import session_scope

        locked_pid = getattr(binding, "locked_provider_id", None)
        locked_model = getattr(binding, "locked_model_name", None)

        if not locked_pid or not locked_model:
            raise LockedModelUnavailableError(
                "Agent locked but no provider_id/model_name specified"
            )

        async with session_scope() as db:
            provider = (await db.execute(
                select(ModelProvider).where(ModelProvider.id == locked_pid)
            )).scalar_one_or_none()

        if provider is None:
            raise LockedModelUnavailableError(
                f"Locked provider (id={locked_pid}) not found"
            )

        if not provider.enabled:
            raise LockedModelUnavailableError(
                f"Locked provider '{provider.name}' is disabled"
            )

    def ensure_lock_invariants(self, binding: object) -> None:
        """Enforce locked mode invariants on save: allow_fallback=False, allow_auto_switch=False."""
        if getattr(binding, "binding_mode", None) != "locked":
            return
        binding.allow_fallback = False  # type: ignore[attr-defined]
        binding.allow_auto_switch = False  # type: ignore[attr-defined]
