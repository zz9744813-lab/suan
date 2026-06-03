"""RewriterAgent — addresses critic issues while preserving the rest."""
from __future__ import annotations

from app.agents.base import BaseAgent


class RewriterAgent(BaseAgent):
    name = "RewriterAgent"
    role = "Rewrite"
    prompt_key = "rewriter_main"
    step_name = "rewrite"
    extra_temperature = 0.0
    extra_max_tokens = 9000
