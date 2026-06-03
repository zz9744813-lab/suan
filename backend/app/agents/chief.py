"""ChiefAgent — global main agent for the right-side chat panel.

The ChiefAgent in MVP returns a structured JSON plan describing actions.
Confirmable actions (create_project, start_worker, etc.) are stored on the
ChiefAgentMessage row and executed by the dedicated routers.
"""
from __future__ import annotations

import json
import re
from typing import Any

from app.agents.base import AgentContext, BaseAgent
from app.core.events import Event, event_bus


class ChiefAgent(BaseAgent):
    name = "ChiefAgent"
    role = "Chief"
    prompt_key = "chief_main"
    step_name = "chat"
    extra_temperature = 0.0
    extra_max_tokens = 2000

    async def after_run(
        self, ctx: AgentContext, parsed: dict[str, Any] | None, raw: str
    ) -> None:
        actions = (parsed or {}).get("actions") or []
        reply = (parsed or {}).get("reply") or ""
        await event_bus.publish(
            Event(
                event_type="chief.reply",
                payload={
                    "project_id": ctx.project_id,
                    "reply_preview": reply[:200],
                    "actions_count": len(actions),
                },
            )
        )


def extract_json_block(text: str) -> dict[str, Any] | None:
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    m = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", text)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            return None
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return None
    return None
