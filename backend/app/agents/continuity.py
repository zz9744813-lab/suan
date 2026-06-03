"""ContinuityAgent — time/state/foreshadow consistency check."""
from __future__ import annotations

from app.agents.base import BaseAgent


class ContinuityAgent(BaseAgent):
    name = "ContinuityAgent"
    role = "Continuity"
    prompt_key = "continuity_main"
    step_name = "continuity"
    extra_temperature = 0.0
    extra_max_tokens = 2500
