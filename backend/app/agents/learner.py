"""LearningAgent — produce a learning report and persist summary fields."""
from __future__ import annotations

from app.agents.base import BaseAgent


class LearningAgent(BaseAgent):
    name = "LearningAgent"
    role = "Learning"
    prompt_key = "learning_main"
    step_name = "learning"
    extra_temperature = 0.0
    extra_max_tokens = 2500
