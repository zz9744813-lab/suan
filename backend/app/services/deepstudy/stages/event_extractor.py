"""Event extractor stage — LLM-driven plot event extraction.

Uses StudyEventAgent's prompt template to extract foreshadowing,
turning points, power-ups, key decisions, and faction shifts from
each chapter. Results are written to ForeshadowChain and also
stored as Entity rows of type 'event'.
"""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select

from .base import BaseStage
from .llm_helper import call_llm, safe_json_loads, truncate_text

logger = logging.getLogger(__name__)


class EventExtractorStage(BaseStage):
    stage_key = "event_extract"

    async def execute_chapter(
        self, db, run, chapter_index: int, chapter_text: str, prev_context=None
    ) -> dict:
        """Extract plot-significant events from a chapter using LLM."""
        from app.models.deepstudy import Entity, ForeshadowChain
        from app.models.study import StudyChapter

        text = truncate_text(chapter_text, max_chars=8000) if chapter_text else ""

        if not text.strip():
            return {
                "events_found": 0,
                "_input_tokens": 0,
                "_output_tokens": 0,
                "_cost_usd": 0.0,
                "_duration_ms": 0,
            }

        # Get existing foreshadows for dedup
        existing_foreshadows = await self._get_existing_foreshadows(db, run.material_id)

        # Call LLM
        try:
            resolved, result = await call_llm(
                db,
                role="StudyAgent",
                prompt_key="study_event",
                inputs={
                    "chapter_no": str(chapter_index),
                    "chapter_text": text,
                    "existing_foreshadows": existing_foreshadows or "暂无已识别伏笔",
                },
                temperature=0.0,
                max_tokens=2500,
                response_format={"type": "json_object"},
            )
            raw = result.content
            parsed = safe_json_loads(raw)
            input_tokens = result.input_tokens or 0
            output_tokens = result.output_tokens or 0
            cost_usd = result.cost_usd or 0.0
            duration_ms = result.duration_ms or 0
        except Exception as exc:
            logger.warning(f"EventExtractor LLM call failed for ch {chapter_index}: {exc}")
            parsed = None
            input_tokens = 0
            output_tokens = 0
            cost_usd = 0.0
            duration_ms = 0

        events_found = 0

        if parsed and "events" in parsed:
            for evt_data in parsed["events"]:
                if not isinstance(evt_data, dict):
                    continue
                name = evt_data.get("name", "").strip()
                if not name:
                    continue

                kind = evt_data.get("kind", "其他")
                importance = int(evt_data.get("importance", 3))
                summary = evt_data.get("summary", "")
                related_chars = evt_data.get("related_characters", [])
                quote = evt_data.get("quote", "")

                # Determine foreshadow status based on kind
                if kind == "伏笔":
                    status = "planted"
                    foreshadow_type = "事件"
                elif kind == "转折":
                    status = "paid_off"
                    foreshadow_type = "事件"
                else:
                    status = "planted"
                    foreshadow_type = "事件"

                # Find related entity IDs
                related_entity_ids = await self._resolve_entity_ids(
                    db, run.material_id, related_chars
                )

                # Create ForeshadowChain
                chain = ForeshadowChain(
                    material_id=run.material_id,
                    name=name,
                    summary=summary,
                    foreshadow_type=foreshadow_type,
                    planted_chapter=chapter_index,
                    status=status,
                    related_entity_ids=related_entity_ids,
                    evidence=[{
                        "chapter": chapter_index,
                        "type": kind,
                        "quote": quote,
                        "summary": summary,
                    }],
                    importance=importance / 5.0,
                    confidence=0.7,
                )
                db.add(chain)

                # Also create an Entity of type 'event' for the graph
                norm_name = name.strip().lower()
                existing_ent = (
                    await db.execute(
                        select(Entity).where(
                            Entity.material_id == run.material_id,
                            Entity.name == name,
                            Entity.entity_type == "event",
                        )
                    )
                ).scalar_one_or_none()

                if not existing_ent:
                    entity = Entity(
                        material_id=run.material_id,
                        entity_type="event",
                        name=name,
                        aliases=[],
                        tags=[kind],
                        profile={"summary": summary, "kind": kind, "importance": importance},
                        first_chapter_index=chapter_index,
                        last_chapter_index=chapter_index,
                        importance=importance / 5.0,
                        confidence=0.6,
                        merge_key=f"{run.material_id}:event:{norm_name}",
                        created_by_agent="EventExtractorStage",
                    )
                    db.add(entity)

                events_found += 1

        # Accumulate cost
        run.input_tokens = (run.input_tokens or 0) + input_tokens
        run.output_tokens = (run.output_tokens or 0) + output_tokens
        run.cost_usd = round((run.cost_usd or 0.0) + cost_usd, 6)

        return {
            "events_found": events_found,
            "_input_tokens": input_tokens,
            "_output_tokens": output_tokens,
            "_cost_usd": cost_usd,
            "_duration_ms": duration_ms,
        }

    async def _get_existing_foreshadows(self, db, material_id: int) -> str:
        """Get a summary of already-extracted foreshadows for dedup."""
        from app.models.deepstudy import ForeshadowChain
        chains = (
            await db.execute(
                select(ForeshadowChain).where(
                    ForeshadowChain.material_id == material_id,
                )
            )
        ).scalars().all()

        if not chains:
            return ""

        lines = []
        for c in chains[:20]:
            line = f"- {c.name}（{c.foreshadow_type}，第{c.planted_chapter}章）"
            lines.append(line)
        return "\n".join(lines)

    async def _resolve_entity_ids(
        self, db, material_id: int, names: list[str]
    ) -> list[int]:
        """Resolve character names to entity IDs."""
        from app.models.deepstudy import Entity
        ids = []
        for name in names:
            name = name.strip()
            if not name:
                continue
            entity = (
                await db.execute(
                    select(Entity).where(
                        Entity.material_id == material_id,
                        Entity.name == name,
                        Entity.entity_type == "character",
                    )
                )
            ).scalar_one_or_none()
            if entity:
                ids.append(entity.id)
        return ids
