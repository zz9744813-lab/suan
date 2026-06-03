"""CriticAgent — multi-dimensional scoring."""
from __future__ import annotations

from typing import Any

from app.agents.base import BaseAgent


class CriticAgent(BaseAgent):
    name = "CriticAgent"
    role = "Critic"
    prompt_key = "critic_main"
    step_name = "review"
    # step-3.7-flash (reasoning model) is unstable for JSON output at
    # any non-zero temperature — it sometimes decides to "explain" the
    # task in prose. Forcing temp=0 makes the JSON path deterministic.
    extra_temperature = 0.0
    extra_max_tokens = 3500

    # P0-4 fix: a missing critic report shouldn't fail the whole
    # chapter. The pipeline can hand a fallback report to the
    # rewriter (which itself can decide to skip) and the user sees a
    # "degraded" status instead of a 400.
    allow_json_fallback = True

    def _build_json_fallback(self, raw: str) -> dict[str, Any]:
        # Shape mirrors the prompt's expected schema so downstream
        # consumers (rewriter / continuity / memory) don't crash on a
        # missing key. ``total`` is set below ``pass_score`` so the
        # rewrite loop will still run if max_rewrite_rounds > 0.
        return {
            "total": 60,
            "scores": {},
            "issues": [
                {
                    "category": "format",
                    "severity": "high",
                    "quote": "",
                    "comment": (
                        "模型未返回合法 JSON，已使用 fallback 评分。"
                        "请检查模型或 Prompt。"
                    ),
                }
            ],
            "rewrite_required": True,
            "summary": "CriticAgent JSON 解析失败，系统已降级处理。",
            "next_chapter_hook": None,
            "parse_failed": True,
            "fallback": True,
            "raw_preview": (raw or "")[:1000],
        }
