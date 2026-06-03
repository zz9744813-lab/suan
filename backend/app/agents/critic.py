"""CriticAgent — multi-dimensional scoring."""
from __future__ import annotations

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
