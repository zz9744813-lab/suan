"""Cost / pricing helpers for popular OpenAI-Compatible models.

Pricing data is a static best-effort table (USD per 1M tokens). Unknown models
fall back to a conservative default so the cost log is never empty.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ModelPricing:
    input_per_1m: float
    output_per_1m: float


# Last updated 2026-05. Keep keys lowercase model names.
_PRICING: dict[str, ModelPricing] = {
    # OpenAI
    "gpt-4o": ModelPricing(2.5, 10.0),
    "gpt-4o-mini": ModelPricing(0.15, 0.6),
    "gpt-4.1": ModelPricing(2.0, 8.0),
    "gpt-4.1-mini": ModelPricing(0.4, 1.6),
    "gpt-4.1-nano": ModelPricing(0.1, 0.4),
    "o3": ModelPricing(10.0, 40.0),
    "o4-mini": ModelPricing(1.1, 4.4),
    # Anthropic
    "claude-3-5-sonnet": ModelPricing(3.0, 15.0),
    "claude-3-5-haiku": ModelPricing(0.8, 4.0),
    "claude-3-7-sonnet": ModelPricing(3.0, 15.0),
    "claude-sonnet-4": ModelPricing(3.0, 15.0),
    "claude-opus-4": ModelPricing(15.0, 75.0),
    # DeepSeek
    "deepseek-chat": ModelPricing(0.27, 1.1),
    "deepseek-reasoner": ModelPricing(0.55, 2.19),
    # Gemini
    "gemini-2.5-pro": ModelPricing(1.25, 10.0),
    "gemini-2.5-flash": ModelPricing(0.3, 2.5),
    # Qwen
    "qwen-max": ModelPricing(2.0, 6.0),
    "qwen-plus": ModelPricing(0.4, 1.2),
    "qwen-turbo": ModelPricing(0.1, 0.3),
}

_DEFAULT_PRICING = ModelPricing(0.5, 1.5)


def lookup_pricing(model: str) -> ModelPricing:
    if not model:
        return _DEFAULT_PRICING
    key = model.strip().lower()
    if key in _PRICING:
        return _PRICING[key]
    # match by substring so "gpt-4o-2024-08-06" still resolves
    for needle, pricing in _PRICING.items():
        if needle in key or key.startswith(needle):
            return pricing
    return _DEFAULT_PRICING


def estimate_cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    p = lookup_pricing(model)
    return round((input_tokens / 1_000_000) * p.input_per_1m + (output_tokens / 1_000_000) * p.output_per_1m, 6)
