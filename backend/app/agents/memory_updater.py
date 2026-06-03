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

    # P0-4c: a missing memory update should be no-op, not a hard
    # 400. The MemoryService.update_from_chapter() call below will
    # then simply skip the chapter and we'll just lose incremental
    # memory writes for that one chapter — fine, the next chapter
    # will catch up. The continuity / chief pages already surface
    # ``parse_failed=True`` as a yellow badge.
    allow_json_fallback = True

    def _build_json_fallback(self, raw: str) -> dict[str, Any]:
        """MemoryUpdate-shaped fallback when the model returned non-JSON.

        Empty update lists are safe — ``MemoryService.update_from_chapter``
        iterates whatever's there and the empty case is a no-op.
        """
        return {
            "character_state_updates": [],
            "foreshadow_updates": [],
            "hard_fact_additions": [],
            "parse_failed": True,
            "fallback": True,
            "raw_preview": (raw or "")[:1000],
            "summary": "MemoryUpdateAgent 返回内容无法解析为 JSON，已跳过本章记忆抽取。",
        }

    async def after_run(
        self, ctx: AgentContext, parsed: dict[str, Any] | None, raw: str
    ) -> None:
        # P0-2 fix: this hook used to read the agent's OWN JSON output
        # (``raw`` / ``parsed["chapter_content"]``) for ``final_text``.
        # That's wrong: the memory should be extracted from the chapter
        # prose the pipeline already settled on, which is passed in via
        # ``ctx.inputs["final_content"]``. Otherwise we end up saving
        # memory derived from the agent's JSON envelope (and missing the
        # story facts that came out of rewrite).
        if ctx.chapter_id is None:
            return
        from app.models.project import Chapter
        chapter = await ctx.db.get(Chapter, ctx.chapter_id)
        if chapter is None:
            return
        parsed = parsed or {}
        # Fallback ladder (preferred first):
        #   1. ``ctx.inputs["final_content"]`` — the pipeline's chosen
        #      final text (may be the raw draft or the post-rewrite
        #      version, whichever ended up as ``final``).
        #   2. ``parsed["final_content"]`` / ``parsed["chapter_content"]``
        #      / ``parsed["content"]`` — for direct callers (tests) that
        #      don't have ctx.inputs.
        #   3. ``raw`` — last-resort.
        final_text = (
            ctx.inputs.get("final_content")
            or parsed.get("final_content")
            or parsed.get("chapter_content")
            or parsed.get("content")
            or raw
            or ""
        )
        if not isinstance(final_text, str):
            final_text = str(final_text)
        final_text = final_text.strip()
        if not final_text:
            return
        await MemoryService().update_from_chapter(
            ctx.db, chapter=chapter, final_text=final_text
        )
