"""DrafterAgent — writes the actual chapter body."""
from __future__ import annotations

from app.agents.base import BaseAgent


class DrafterAgent(BaseAgent):
    name = "DrafterAgent"
    role = "Draft"
    prompt_key = "drafter_main"
    step_name = "draft"
    uses_json_output = False  # free-form text
    extra_temperature = 0.9
    extra_max_tokens = 5000
