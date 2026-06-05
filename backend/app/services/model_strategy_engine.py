"""ModelStrategyEngine — 根据健康分和策略计算最佳模型.

Strategy types:
- quality_first: 最高 health_score 优先
- speed_first: 最低延迟优先
- cost_first: 最低价格优先
- stable_first: 最高稳定性优先（连续成功次数最多）
- json_first: supports_json=True 优先
- creative_writing: 写作能力优先（大 context_window, text capable）
- strict_review: 结构化输出优先（JSON + stability）
- deepstudy_batch: 批量任务优先（低成本 + 稳定）

Agent default strategies:
- Planner → stable_first
- Drafter → creative_writing
- Critic → strict_review
- Reader → cost_first / speed_first
- Continuity → json_first
- MemoryUpdate → json_first
- DeepStudy → deepstudy_batch
- Discussion → stable_first
"""

from __future__ import annotations

from typing import Any

from app.models.model_health import ModelHealthSnapshot


STRATEGY_DEFAULTS: dict[str, str] = {
    "planner": "stable_first",
    "draft": "creative_writing",
    "critic": "strict_review",
    "rewrite": "creative_writing",
    "continuity": "json_first",
    "memory_update": "json_first",
    "learning": "json_first",
    "reader": "cost_first",
    "discussion": "stable_first",
    "deepstudy": "deepstudy_batch",
}


class ModelStrategyEngine:
    """Rank models by strategy and return sorted candidates."""

    def rank(
        self,
        candidates: list["ModelHealthSnapshot"],
        strategy: str,
        **ctx,
    ) -> list["ModelHealthSnapshot"]:
        """Sort candidates by strategy-specific scoring.

        Higher score = better fit. Returns sorted list (best first).
        """
        if not candidates:
            return []

        if strategy == "speed_first":
            return sorted(candidates, key=lambda m: m.avg_latency_ms or 99999)
        elif strategy == "cost_first":
            return sorted(candidates, key=lambda m: (
                (m.input_price_per_million or 0) + (m.output_price_per_million or 0)
            ))
        elif strategy == "stable_first":
            return sorted(candidates, key=lambda m: (
                -m.success_rate,
                m.consecutive_failures or 0,
                -(m.health_score or 0),
            ))
        elif strategy == "json_first":
            return sorted(candidates, key=lambda m: (
                -int(m.supports_json),
                -(m.health_score or 0),
            ))
        elif strategy == "long_context_first":
            return sorted(candidates, key=lambda m: (
                -(m.context_window or 0),
                -(m.health_score or 0),
            ))
        elif strategy == "creative_writing":
            return sorted(candidates, key=lambda m: (
                -int(m.supports_text),
                -(m.max_output_tokens or 0),
                -(m.health_score or 0),
            ))
        elif strategy == "strict_review":
            return sorted(candidates, key=lambda m: (
                -int(m.supports_json),
                -m.success_rate,
                -(m.health_score or 0),
            ))
        elif strategy == "deepstudy_batch":
            return sorted(candidates, key=lambda m: (
                (m.input_price_per_million or 0) + (m.output_price_per_million or 0),
                -(m.health_score or 0),
                m.avg_latency_ms or 99999,
            ))
        else:
            # quality_first (default)
            return sorted(candidates, key=lambda m: -(m.health_score or 0))

    def get_strategy_for_agent(self, agent_role_key: str) -> str:
        """Map agent_role_key to default strategy."""
        key_lower = agent_role_key.lower().replace("agent_", "")
        for k, v in STRATEGY_DEFAULTS.items():
            if k in key_lower:
                return v
        return "quality_first"  # fallback
