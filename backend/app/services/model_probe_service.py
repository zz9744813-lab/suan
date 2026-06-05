"""ModelProbeService — 执行单模型探测请求.

Lightweight probe to determine model health:
- Send a minimal JSON-only request
- Parse response, measure latency
- Return health snapshot data
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ModelProbeResult:
    """Result of a single model probe."""
    ok: bool
    model_name: str
    provider_id: int
    status: str  # healthy / degraded / failing / rate_limited
    latency_ms: int
    has_text: bool = False
    has_json: bool = False
    error_code: str | None = None
    error_message: str | None = None
    raw_preview: str | None = None
    health_score: float = 0.0


@dataclass
class BatchProbeResult:
    """Result of probing all models on a provider."""
    provider_id: int
    total: int
    passed: int
    failed: int
    items: list[ModelProbeResult] = field(default_factory=list)
    total_latency_ms: int = 0


class ModelProbeService:
    """Send probe requests to individual models and parse results."""

    # Probe prompt: minimal JSON-only to test basic functionality
    PROBE_PROMPT = '{"ok":true,"model":"__model_name__"}'
    PROBE_MAX_TOKENS = 50
    PROBE_TIMEOUT = 15.0  # seconds

    async def probe_model(
        self,
        provider_id: int,
        model_name: str,
        base_url: str,
        api_key: str,
    ) -> ModelProbeResult:
        """Send a minimal JSON probe to a specific model."""
        from app.services.llm.client import (
            LLMAuthError,
            LLMConnectionError,
            LLMRateLimitError,
            LLMRequest,
            LLMMessage,
            get_llm_client,
        )

        client = get_llm_client()
        prompt = self.PROBE_PROMPT.replace("__model_name__", model_name)
        messages = [LLMMessage(role="user", content=prompt)]
        request = LLMRequest(
            model=model_name,
            messages=messages,
            temperature=0.0,
            max_tokens=self.PROBE_MAX_TOKENS,
            response_format={"type": "json_object"},
        )

        t0 = time.perf_counter()
        try:
            coro = client.chat(base_url=base_url, api_key=api_key, request=request)
            result = await asyncio.wait_for(coro, timeout=self.PROBE_TIMEOUT)
            latency_ms = int((time.perf_counter() - t0) * 1000)

            # Parse JSON response
            content = (result.content or "").strip()
            has_text = len(content) > 0
            has_json = False
            try:
                if content.startswith("```"):
                    first_nl = content.find("\n")
                    if first_nl != -1:
                        content = content[first_nl + 1:]
                    if content.endswith("```"):
                        content = content[:-3]
                    content = content.strip()
                json.loads(content)
                has_json = True
            except (json.JSONDecodeError, Exception):
                pass

            return ModelProbeResult(
                ok=True,
                model_name=model_name,
                provider_id=provider_id,
                status="healthy",
                latency_ms=latency_ms,
                has_text=has_text,
                has_json=has_json,
                raw_preview=content[:200] if content else None,
                health_score=1.0 if has_json else 0.7,
            )

        except asyncio.TimeoutError:
            latency_ms = int((time.perf_counter() - t0) * 1000)
            return ModelProbeResult(
                ok=False,
                model_name=model_name,
                provider_id=provider_id,
                status="degraded",
                latency_ms=latency_ms,
                error_message=f"timeout after {self.PROBE_TIMEOUT}s",
                health_score=0.3,
            )

        except LLMRateLimitError as exc:
            latency_ms = int((time.perf_counter() - t0) * 1000)
            return ModelProbeResult(
                ok=False,
                model_name=model_name,
                provider_id=provider_id,
                status="rate_limited",
                latency_ms=latency_ms,
                error_code="rate_limit",
                error_message=str(exc),
                health_score=0.4,
            )

        except LLMAuthError as exc:
            return ModelProbeResult(
                ok=False,
                model_name=model_name,
                provider_id=provider_id,
                status="failing",
                latency_ms=0,
                error_code="auth_failed",
                error_message=str(exc),
                health_score=0.0,
            )

        except LLMConnectionError as exc:
            latency_ms = int((time.perf_counter() - t0) * 1000)
            return ModelProbeResult(
                ok=False,
                model_name=model_name,
                provider_id=provider_id,
                status="failing",
                latency_ms=latency_ms,
                error_code="connection_failed",
                error_message=str(exc),
                health_score=0.0,
            )

        except Exception as exc:
            latency_ms = int((time.perf_counter() - t0) * 1000)
            return ModelProbeResult(
                ok=False,
                model_name=model_name,
                provider_id=provider_id,
                status="failing",
                latency_ms=latency_ms,
                error_message=str(exc),
                health_score=0.0,
            )
