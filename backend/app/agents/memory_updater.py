"""MemoryUpdateAgent — extract facts from the final text and persist them."""
from __future__ import annotations

from typing import Any

from app.agents.base import AgentContext, BaseAgent
from app.services.memory import MemoryService


class MemoryUpdateAgent(BaseAgent):
    name = "MemoryUpdateAgent"
    role = "MemoryUpdate"
    prompt_key = "memory_update_main"
    step_name = "memory_update"
    extra_temperature = 0.0
    extra_max_tokens = 2000

    async def after_run(
        self, ctx: AgentContext, parsed: dict[str, Any] | None, raw: str
    ) -> None:
        # the LLM step already ran. For MVP we apply a deterministic extractor
        # in addition so the memory system has something to show even when the
        # model returns sparse JSON.
        if ctx.chapter_id is None or parsed is None:
            return
        from app.models.project import Chapter
        chapter = await ctx.db.get(Chapter, ctx.chapter_id)
        if chapter is None:
            return
        final_text = (parsed.get("chapter_content") or raw or "").strip()
        if not final_text:
            return
        await MemoryService().update_from_chapter(
            ctx.db, chapter=chapter, final_text=final_text
        )
