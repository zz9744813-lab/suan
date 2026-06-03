"""PlannerAgent — generates a chapter plan from the context package."""
from __future__ import annotations

from app.agents.base import BaseAgent


class PlannerAgent(BaseAgent):
    name = "PlannerAgent"
    role = "Planner"
    prompt_key = "planner_main"
    step_name = "plan"
    # step-3.7-flash is a reasoning model that occasionally decides to
    # "explain" the task in prose instead of emitting JSON. Forcing a
    # low temperature makes the JSON output path (mostly) deterministic;
    # the LLM client also injects a strict JSON-only system message.
    extra_temperature = 0.0
    extra_max_tokens = 3500
