"""Scene beat extractor stage — LLM-driven scene beat extraction.

Identifies atomic narrative beats (trigger → action → result) within
each chapter and persists them to the SceneBeat table. These beats
form the middle layer of the knowledge graph between chapters and
entities.
"""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select

from .base import BaseStage
from .llm_helper import call_llm, safe_json_loads, truncate_text

logger = logging.getLogger(__name__)


class SceneBeatExtractorStage(BaseStage):
    stage_key = "scene_beat_extract"

    async def execute_chapter(
        self, db, run, chapter_index: int, chapter_text: str, prev_context=None
    ) -> dict:
        """Extract scene beats from a chapter using LLM."""
        from app.models.deepstudy import SceneBeat, Entity
        from app.models.study import StudyChapter

        text = truncate_text(chapter_text, max_chars=8000) if chapter_text else ""

        if not text.strip():
            return {
                "beats_found": 0,
                "_input_tokens": 0,
                "_output_tokens": 0,
                "_cost_usd": 0.0,
                "_duration_ms": 0,
            }

        # Get known character names for entity resolution
        char_names = await self._get_character_names(db, run.material_id)

        # Call LLM
        try:
            resolved, result = await call_llm(
                db,
                role="StudyAgent",
                prompt_key="study_scene_beat",
                inputs={
                    "chapter_no": str(chapter_index),
                    "chapter_text": text,
                    "known_characters": char_names or "暂无已识别人物",
                },
                temperature=0.0,
                max_tokens=3000,
                response_format={"type": "json_object"},
            )
            raw = result.content
            parsed = safe_json_loads(raw)
            input_tokens = result.input_tokens or 0
            output_tokens = result.output_tokens or 0
            cost_usd = result.cost_usd or 0.0
            duration_ms = result.duration_ms or 0
        except Exception as exc:
            logger.warning(f"SceneBeatExtractor LLM call failed for ch {chapter_index}: {exc}")
            parsed = None
            input_tokens = 0
            output_tokens = 0
            cost_usd = 0.0
            duration_ms = 0

        beats_found = 0

        # Look up chapter for FK
        chapter = (
            await db.execute(
                select(StudyChapter).where(
                    StudyChapter.material_id == run.material_id,
                    StudyChapter.chapter_index == chapter_index,
                )
            )
        ).scalar_one_or_none()

        if parsed and "beats" in parsed and chapter is not None:
            for idx, beat_data in enumerate(parsed["beats"]):
                if not isinstance(beat_data, dict):
                    continue

                title = beat_data.get("title", f"节拍{idx + 1}").strip()
                if not title:
                    title = f"节拍{idx + 1}"

                # Resolve character names to entity IDs
                involved_names = beat_data.get("involved_characters", [])
                involved_entity_ids = await self._resolve_entity_ids(
                    db, run.material_id, involved_names
                )

                # Extract evidence quotes
                evidence_quotes = beat_data.get("evidence_quotes", [])
                if isinstance(evidence_quotes, str):
                    evidence_quotes = [evidence_quotes]

                beat = SceneBeat(
                    material_id=run.material_id,
                    chapter_id=chapter.id,
                    chapter_index=chapter_index,
                    beat_index=idx + 1,
                    title=title,
                    summary=beat_data.get("summary", ""),
                    scene_type=beat_data.get("scene_type", "铺垫"),
                    conflict=beat_data.get("conflict"),
                    trigger=beat_data.get("trigger"),
                    action=beat_data.get("action"),
                    result=beat_data.get("result"),
                    reader_emotion=beat_data.get("reader_emotion"),
                    involved_entity_ids=involved_entity_ids,
                    evidence_quotes=evidence_quotes,
                    importance=float(beat_data.get("importance", 0.5)),
                    confidence=0.7,
                    raw_result=beat_data,
                )
                db.add(beat)
                beats_found += 1

        # Accumulate cost
        run.input_tokens = (run.input_tokens or 0) + input_tokens
        run.output_tokens = (run.output_tokens or 0) + output_tokens
        run.cost_usd = round((run.cost_usd or 0.0) + cost_usd, 6)

        return {
            "beats_found": beats_found,
            "_input_tokens": input_tokens,
            "_output_tokens": output_tokens,
            "_cost_usd": cost_usd,
            "_duration_ms": duration_ms,
        }

    async def _get_character_names(self, db, material_id: int) -> str:
        """Get known character names for the prompt."""
        entities = (
            await db.execute(
                select(Entity).where(
                    Entity.material_id == material_id,
                    Entity.entity_type == "character",
                )
            )
        ).scalars().all()

        if not entities:
            return ""
        return "、".join(e.name for e in entities[:30])

    async def _resolve_entity_ids(
        self, db, material_id: int, names: list[str]
    ) -> list[int]:
        """Resolve character names to entity IDs."""
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
                    )
                )
            ).scalar_one_or_none()
            if entity:
                ids.append(entity.id)
        return ids
