"""Model provider / role assignment (spec §14.3)."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def _utcnow() -> datetime:
    return datetime.utcnow()


class ModelProvider(Base):
    """OpenAI-Compatible provider configuration (spec §1.3 / §16)."""

    __tablename__ = "model_providers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    base_url: Mapped[str] = mapped_column(String(500))
    api_key: Mapped[str] = mapped_column(String(500))
    default_model: Mapped[str] = mapped_column(String(120), default="")
    model_list: Mapped[list[str]] = mapped_column(JSON, default=list)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_test_status: Mapped[str | None] = mapped_column(String(20), default=None)
    last_test_message: Mapped[str | None] = mapped_column(Text, default=None)
    last_test_at: Mapped[datetime | None] = mapped_column(default=None)
    # P0-MODEL-3: lightweight per-model health probe (ping).
    # Distinct from ``last_test_*`` which is a full ``/v1/models`` call.
    last_health_status: Mapped[str | None] = mapped_column(String(20), default=None)
    last_health_message: Mapped[str | None] = mapped_column(Text, default=None)
    last_health_latency_ms: Mapped[int | None] = mapped_column(Integer, default=None)
    last_health_model: Mapped[str | None] = mapped_column(String(120), default=None)
    last_health_at: Mapped[datetime | None] = mapped_column(default=None)
    extra: Mapped[dict | None] = mapped_column(JSON, default=None)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=_utcnow, onupdate=_utcnow)

    roles: Mapped[list["ModelRoleAssignment"]] = relationship(back_populates="provider", cascade="all, delete-orphan")


class ModelRoleAssignment(Base):
    """Map an agent role (ChiefAgent, DraftAgent, ...) to a provider+model."""

    __tablename__ = "model_role_assignments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    role: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    provider_id: Mapped[int] = mapped_column(ForeignKey("model_providers.id", ondelete="CASCADE"))
    model: Mapped[str] = mapped_column(String(120))
    temperature: Mapped[float] = mapped_column(Float, default=0.8)
    max_tokens: Mapped[int] = mapped_column(Integer, default=2048)
    notes: Mapped[str | None] = mapped_column(Text, default=None)
    updated_at: Mapped[datetime] = mapped_column(default=_utcnow, onupdate=_utcnow)

    provider: Mapped["ModelProvider"] = relationship(back_populates="roles")
