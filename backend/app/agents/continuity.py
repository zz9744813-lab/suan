"""ContinuityAgent — time/state/foreshadow consistency check."""
from __future__ import annotations

from typing import Any

from app.agents.base import BaseAgent


class ContinuityAgent(BaseAgent):
    name = "ContinuityAgent"
    role = "Continuity"
    prompt_key = "continuity_main"
    step_name = "continuity"
    extra_temperature = 0.0
    extra_max_tokens = 2500

    # P0-4b: step-3.7-flash (reasoning model) often forgets to wrap its
    # answer in JSON, especially for free-form tasks like continuity
    # checking where the model "feels like explaining first". A missing
    # continuity report shouldn't take down the whole chapter — the
    # pipeline only uses the parsed shape for cost/tokens aggregation
    # and a soft UI hint. Flip on the fallback so we degrade gracefully
    # with ``conflicts: []`` and ``ok: True`` (no false alarms) instead
    # of a hard 400.
    allow_json_fallback = True

    def _build_json_fallback(self, raw: str) -> dict[str, Any]:
        """Continuity-shaped fallback when the model returned non-JSON.

        Shape mirrors the prompt's expected schema so anything that
        later pokes at ``conflicts`` / ``missing_advances`` / ``ok``
        doesn't crash. ``ok: True`` is a deliberate "we don't know, so
        don't accuse the draft" default — better to miss a real
        continuity bug than to wrongly flag clean prose. The actual
        raw output is preserved in ``raw_preview`` so the UI / chief
        can still surface what the model said.
        """
        return {
            "conflicts": [],
            "missing_advances": [],
            "ok": True,
            "summary": "ContinuityAgent 返回内容无法解析为 JSON，已使用 fallback（不报警）。",
            "parse_failed": True,
            "fallback": True,
            "raw_preview": (raw or "")[:1000],
        }
