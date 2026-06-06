"""Entity extractor stage — LLM-driven character and entity extraction.

Replaces the old regex-based stub with real LLM calls using
StudyCharacterAgent's prompt template. Each chapter is processed
independently; entities are merged by name across chapters.
"""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select

from .base import BaseStage
from .llm_helper import call_llm, safe_json_loads, truncate_text

logger = logging.getLogger(__name__)


class EntityExtractorStage(BaseStage):
    stage_key = "entity_extract"

    async def execute_chapter(
        self, db, run, chapter_index: int, chapter_text: str, prev_context=None
    ) -> dict:
        """Extract characters and entities from a chapter using LLM."""
        from app.models.deepstudy import Entity, EntityMention
        from app.models.study import StudyChapter

        text = truncate_text(chapter_text, max_chars=8000) if chapter_text else ""

        if not text.strip():
            return {
                "entities_found": 0,
                "_input_tokens": 0,
                "_output_tokens": 0,
                "_cost_usd": 0.0,
                "_duration_ms": 0,
            }

        # Build context of already-known characters for merging
        existing_chars = await self._get_existing_characters(db, run.material_id)

        # Call LLM
        try:
            resolved, result = await call_llm(
                db,
                role="StudyAgent",
                prompt_key="study_character",
                inputs={
                    "chapter_text": text,
                    "existing_characters": existing_chars or "暂无已识别人物",
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
            logger.warning(f"EntityExtractor LLM call failed for ch {chapter_index}: {exc}")
            parsed = None
            input_tokens = 0
            output_tokens = 0
            cost_usd = 0.0
            duration_ms = 0

        # Parse and persist entities
        entities_found = 0
        chapter = (
            await db.execute(
                select(StudyChapter).where(
                    StudyChapter.material_id == run.material_id,
                    StudyChapter.chapter_index == chapter_index,
                )
            )
        ).scalar_one_or_none()

        if parsed and "characters" in parsed:
            for char_data in parsed["characters"]:
                if not isinstance(char_data, dict):
                    continue
                name = char_data.get("name", "").strip()
                if not name:
                    continue

                entity = await self._upsert_entity(
                    db, run.material_id, name, char_data, chapter_index
                )
                entities_found += 1

                # Create mention
                if chapter is not None and entity is not None:
                    # Find a quote from the text if available
                    quote = char_data.get("base_profile", {})
                    if isinstance(quote, dict):
                        quote = ""
                    evidence = char_data.get("summary", "")
                    mention = EntityMention(
                        entity_id=entity.id,
                        material_id=run.material_id,
                        chapter_id=chapter.id,
                        mention_type="appearance",
                        confidence=float(char_data.get("confidence", 0.7)) if "confidence" in char_data else 0.7,
                        quote=evidence or "",
                    )
                    db.add(mention)

        # Also extract non-character entities (locations, factions, items)
        # via a secondary LLM call with a different prompt
        non_char_count = await self._extract_non_character_entities(
            db, run, chapter_index, text, chapter
        )
        entities_found += non_char_count

        # Accumulate cost on the run
        run.input_tokens = (run.input_tokens or 0) + input_tokens
        run.output_tokens = (run.output_tokens or 0) + output_tokens
        run.cost_usd = round((run.cost_usd or 0.0) + cost_usd, 6)

        return {
            "entities_found": entities_found,
            "_input_tokens": input_tokens,
            "_output_tokens": output_tokens,
            "_cost_usd": cost_usd,
            "_duration_ms": duration_ms,
        }

    async def _get_existing_characters(self, db, material_id: int) -> str:
        """Get a summary of already-extracted characters for the prompt."""
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

        lines = []
        for e in entities[:30]:  # Limit to avoid prompt overflow
            aliases = ", ".join(e.aliases or [])
            line = f"- {e.name}"
            if aliases:
                line += f"（别名：{aliases}）"
            tags = ", ".join(e.tags or [])
            if tags:
                line += f" [{tags}]"
            lines.append(line)
        return "\n".join(lines)

    async def _upsert_entity(
        self, db, material_id: int, name: str, char_data: dict, chapter_index: int
    ) -> Entity | None:
        """Create or merge an entity for the given character."""
        # Check for existing entity with same name
        existing = (
            await db.execute(
                select(Entity).where(
                    Entity.material_id == material_id,
                    Entity.name == name,
                )
            )
        ).scalar_one_or_none()

        if existing:
            # Merge: update last_chapter_index and merge aliases/tags
            existing.last_chapter_index = chapter_index
            new_aliases = char_data.get("aliases", [])
            if isinstance(new_aliases, list) and new_aliases:
                merged = list(set((existing.aliases or []) + new_aliases))
                existing.aliases = merged
            new_tags = char_data.get("tags", [])
            if isinstance(new_tags, list) and new_tags:
                merged = list(set((existing.tags or []) + new_tags))
                existing.tags = merged
            # Update profile if we got new data
            profile = char_data.get("base_profile", {})
            if isinstance(profile, dict) and profile:
                existing.profile = profile
            role = char_data.get("role", "")
            if role:
                if not existing.profile:
                    existing.profile = {}
                existing.profile["role"] = role
            await db.flush()
            return existing

        # Create new entity
        norm_name = name.strip().lower()
        entity = Entity(
            material_id=material_id,
            entity_type="character",
            name=name,
            aliases=char_data.get("aliases", []),
            tags=char_data.get("tags", []),
            profile=char_data.get("base_profile", {}),
            first_chapter_index=chapter_index,
            last_chapter_index=chapter_index,
            importance=0.5,
            confidence=0.7,
            merge_key=f"{material_id}:character:{norm_name}",
            created_by_agent="StudyCharacterAgent",
        )
        db.add(entity)
        await db.flush()
        return entity

    async def _extract_non_character_entities(
        self, db, run, chapter_index: int, text: str, chapter
    ) -> int:
        """Extract locations, factions, items from chapter text via LLM."""
        if not text.strip():
            return 0

        try:
            resolved, result = await call_llm(
                db,
                role="StudyAgent",
                prompt_key="study_entity_extract",
                inputs={
                    "chapter_text": truncate_text(text, 4000),
                },
                temperature=0.0,
                max_tokens=1500,
                response_format={"type": "json_object"},
            )
            parsed = safe_json_loads(result.content)

            # Accumulate cost
            run.input_tokens = (run.input_tokens or 0) + (result.input_tokens or 0)
            run.output_tokens = (run.output_tokens or 0) + (result.output_tokens or 0)
            run.cost_usd = round(
                (run.cost_usd or 0.0) + (result.cost_usd or 0.0), 6
            )
        except Exception as exc:
            logger.warning(f"Non-char entity extraction failed for ch {chapter_index}: {exc}")
            return 0

        if not parsed or "entities" not in parsed:
            return 0

        count = 0
        for ent_data in parsed["entities"]:
            if not isinstance(ent_data, dict):
                continue
            name = ent_data.get("name", "").strip()
            ent_type = ent_data.get("type", "location").strip()
            if not name or ent_type == "character":
                continue  # Characters handled by main extraction

            # Upsert
            existing = (
                await db.execute(
                    select(Entity).where(
                        Entity.material_id == run.material_id,
                        Entity.name == name,
                        Entity.entity_type == ent_type,
                    )
                )
            ).scalar_one_or_none()

            if existing:
                existing.last_chapter_index = chapter_index
            else:
                norm_name = name.strip().lower()
                entity = Entity(
                    material_id=run.material_id,
                    entity_type=ent_type,
                    name=name,
                    aliases=[],
                    tags=ent_data.get("tags", []),
                    profile={"summary": ent_data.get("summary", "")},
                    first_chapter_index=chapter_index,
                    last_chapter_index=chapter_index,
                    importance=0.3,
                    confidence=float(ent_data.get("confidence", 0.5)),
                    merge_key=f"{run.material_id}:{ent_type}:{norm_name}",
                    created_by_agent="EntityExtractorStage",
                )
                db.add(entity)
                await db.flush()

                # Create mention
                if chapter is not None:
                    mention = EntityMention(
                        entity_id=entity.id,
                        material_id=run.material_id,
                        chapter_id=chapter.id,
                        mention_type="appearance",
                        confidence=0.5,
                        quote=ent_data.get("evidence", ""),
                    )
                    db.add(mention)

            count += 1

        return count
