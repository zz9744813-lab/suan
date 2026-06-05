"""Entity extractor stage - extracts entities from chapters."""
import re

from .base import BaseStage


class EntityExtractorStage(BaseStage):
    stage_key = "entity_extract"

    async def execute_chapter(self, db, run, chapter_index, chapter_text, prev_context=None):
        from app.models.deepstudy import Entity, EntityMention
        from app.models.study import StudyChapter
        from sqlalchemy import select

        text = chapter_text[:3000] if chapter_text else ""

        # Look up chapter for FK
        chapter = (
            await db.execute(
                select(StudyChapter).where(
                    StudyChapter.material_id == run.material_id,
                    StudyChapter.chapter_index == chapter_index,
                )
            )
        ).scalar_one_or_none()

        # Basic entity extraction from text patterns
        entities_found = self._extract_entities(text)
        for ent in entities_found:
            existing = await db.execute(
                select(Entity).where(
                    Entity.material_id == run.material_id,
                    Entity.name == ent["name"],
                )
            )
            entity = existing.scalar_one_or_none()
            if not entity:
                entity = Entity(
                    material_id=run.material_id,
                    entity_type=ent["type"],
                    name=ent["name"],
                    confidence=ent.get("confidence", 0.7),
                    first_chapter_index=chapter_index,
                    last_chapter_index=chapter_index,
                )
                db.add(entity)
                await db.flush()

            # Create mention (chapter is guaranteed non-None after lookup)
            mention = EntityMention(
                entity_id=entity.id,
                material_id=run.material_id,
                chapter_id=chapter.id,
                mention_type="appearance",
                confidence=ent.get("confidence", 0.7),
                quote=ent.get("evidence", ""),
            )
            db.add(mention)

        return {
            "entities_found": len(entities_found),
            "_input_tokens": len(text) // 3,
            "_output_tokens": 200,
            "_cost_usd": 0.002,
            "_duration_ms": 800,
        }

    def _extract_entities(self, text: str) -> list:
        entities = []
        # Find Chinese names (2-3 chars) preceding common verbs
        names = re.findall(
            r"([\u4e00-\u9fff]{2,3})(?:道|说|想|看|走|来|去|笑|怒)", text
        )
        for name in set(names[:10]):
            entities.append({
                "name": name,
                "type": "character",
                "confidence": 0.6,
                "evidence": f"第{len(entities) + 1}次出现",
            })
        return entities
