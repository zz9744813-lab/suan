"""Exact LLM response cache.

The cache key is a stable hash of the semantic request payload:
provider/model, role, messages, sampling options, response format, and
extra body.  It intentionally does not try semantic similarity; this is
only for deterministic request de-duplication and retry recovery.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def _utcnow() -> datetime:
    return datetime.utcnow()


class LLMCacheEntry(Base):
    __tablename__ = "llm_cache_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    request_id: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    request_hash: Mapped[str] = mapped_column(String(80), unique=True, index=True)

    provider_id: Mapped[int | None] = mapped_column(Integer, default=None, index=True)
    provider_name: Mapped[str | None] = mapped_column(String(120), default=None)
    model_name: Mapped[str | None] = mapped_column(String(200), default=None, index=True)
    agent_role_key: Mapped[str | None] = mapped_column(String(80), default=None, index=True)
    step_key: Mapped[str | None] = mapped_column(String(80), default=None, index=True)

    request_json: Mapped[dict | None] = mapped_column(JSON, default=None)
    response_content: Mapped[str] = mapped_column(Text, default="")
    response_raw: Mapped[dict | None] = mapped_column(JSON, default=None)
    response_model: Mapped[str | None] = mapped_column(String(200), default=None)

    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)

    hit_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(default=_utcnow, onupdate=_utcnow)
    last_hit_at: Mapped[datetime | None] = mapped_column(default=None)
