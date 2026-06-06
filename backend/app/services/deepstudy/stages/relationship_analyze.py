"""Relationship analyze stage — LLM-driven semantic relationship extraction.

This stage operates at the book level (not per-chapter). It:
1. Finds all co-occurring character pairs from the entity + mention data.
2. For each pair, calls StudyRelationshipExtractionAgent to get the
   semantic relationship type (师父/对手/恋人/...).
3. Persists results to the Relationship table.

This replaces the old co-occurrence-only approach with real LLM-driven
semantic extraction.
"""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import func, select

from .base import BaseStage
from .llm_helper import call_llm, safe_json_loads, truncate_text

logger = logging.getLogger(__name__)

# Max pairs to process per run (avoid runaway cost on books with many characters)
MAX_PAIRS_PER_RUN = 60
# Min shared chapters for a pair to be considered
MIN_SHARED_CHAPTERS = 1


class RelationshipAnalyzeStage(BaseStage):
    stage_key = "relationship_analyze"

    async def execute_chapter(
        self, db, run, chapter_index: int, chapter_text: str, prev_context=None
    ) -> dict:
        """Not used — this stage operates at book level via execute_stage."""
        return {"skipped": True}

    async def execute_stage(self, db, run, stage_result_store) -> None:
        """Extract relationships between co-occurring character pairs.

        Overrides BaseStage.execute_stage because this is a book-level
        operation, not a per-chapter one.
        """
        from app.models.deepstudy import Entity, EntityMention, Relationship, DeepStudyStageResult
        from app.models.study import StudyChapter

        material_id = run.material_id

        # 1. Get all character entities
        characters = (
            await db.execute(
                select(Entity).where(
                    Entity.material_id == material_id,
                    Entity.entity_type == "character",
                )
            )
        ).scalars().all()

        if len(characters) < 2:
            # Not enough characters for relationships
            await self._mark_completed(db, run)
            return

        # 2. Build co-occurrence matrix from mentions
        pair_chapters = await self._build_cooccurrence(db, material_id, characters)

        if not pair_chapters:
            await self._mark_completed(db, run)
            return

        # 3. Sort pairs by co-occurrence count (descending) and limit
        sorted_pairs = sorted(
            pair_chapters.items(),
            key=lambda x: len(x[1]),
            reverse=True,
        )[:MAX_PAIRS_PER_RUN]

        # 4. For each pair, call LLM to extract semantic relationship
        total_input_tokens = 0
        total_output_tokens = 0
        total_cost_usd = 0.0
        total_duration_ms = 0
        relationships_found = 0

        for (char_a_id, char_b_id), shared_chapter_indices in sorted_pairs:
            char_a = next((c for c in characters if c.id == char_a_id), None)
            char_b = next((c for c in characters if c.id == char_b_id), None)
            if char_a is None or char_b is None:
                continue

            # Get chapter excerpts where both appear
            excerpt = await self._get_shared_excerpt(
                db, material_id, shared_chapter_indices
            )

            if not excerpt.strip():
                continue

            # Call LLM
            try:
                resolved, result = await call_llm(
                    db,
                    role="StudyAgent",
                    prompt_key="study_relationship",
                    inputs={
                        "char_a_name": char_a.name,
                        "char_b_name": char_b.name,
                        "char_a_role": (char_a.profile or {}).get("role", "未知"),
                        "char_b_role": (char_b.profile or {}).get("role", "未知"),
                        "chapter_excerpt": truncate_text(excerpt, 4000),
                    },
                    temperature=0.0,
                    max_tokens=1500,
                    response_format={"type": "json_object"},
                )
                raw = result.content
                parsed = safe_json_loads(raw)
                total_input_tokens += result.input_tokens or 0
                total_output_tokens += result.output_tokens or 0
                total_cost_usd += result.cost_usd or 0.0
                total_duration_ms += result.duration_ms or 0
            except Exception as exc:
                logger.warning(
                    f"Relationship LLM call failed for {char_a.name}↔{char_b.name}: {exc}"
                )
                parsed = None

            if not parsed or "relations" not in parsed:
                continue

            for rel_data in parsed["relations"]:
                if not isinstance(rel_data, dict):
                    continue
                relation = rel_data.get("relation", "未知")
                if relation == "未知":
                    continue

                # Map Chinese relation to enum type
                relation_type = self._map_relation_type(relation)
                confidence = float(rel_data.get("confidence", 0.5))
                evidence = rel_data.get("evidence", "")

                # Check for existing relationship
                existing = (
                    await db.execute(
                        select(Relationship).where(
                            Relationship.material_id == material_id,
                            Relationship.source_entity_id == char_a_id,
                            Relationship.target_entity_id == char_b_id,
                            Relationship.relation_type == relation_type,
                        )
                    )
                ).scalar_one_or_none()

                if existing:
                    # Update with stronger evidence if higher confidence
                    if confidence > existing.confidence:
                        existing.confidence = confidence
                        existing.evidence_quotes = [evidence] if evidence else []
                        existing.relation_label = relation
                    continue

                # Determine direction
                direction = "bidirectional"
                if relation in ("师父", "弟子", "主仆", "父子", "母子"):
                    direction = "a_to_b"  # A is master/parent of B

                rel = Relationship(
                    material_id=material_id,
                    source_entity_id=char_a_id,
                    target_entity_id=char_b_id,
                    relation_type=relation_type,
                    relation_label=relation,
                    direction=direction,
                    strength=confidence,
                    chapter_start=min(shared_chapter_indices),
                    chapter_end=max(shared_chapter_indices),
                    status="confirmed" if confidence >= 0.7 else "candidate",
                    evidence_quotes=[evidence] if evidence else [],
                    confidence=confidence,
                    created_by_agent="RelationshipAnalyzeStage",
                )
                db.add(rel)
                relationships_found += 1

        # Accumulate cost
        run.input_tokens = (run.input_tokens or 0) + total_input_tokens
        run.output_tokens = (run.output_tokens or 0) + total_output_tokens
        run.cost_usd = round((run.cost_usd or 0.0) + total_cost_usd, 6)
        run.processed_chapters = run.total_chapters

        # Record stage result
        sr = DeepStudyStageResult(
            run_id=run.id,
            material_id=material_id,
            stage_key=self.stage_key,
            status="succeeded",
            output_json={
                "relationships_found": relationships_found,
                "pairs_analyzed": len(sorted_pairs),
            },
            input_tokens=total_input_tokens,
            output_tokens=total_output_tokens,
            cost_usd=total_cost_usd,
            duration_ms=total_duration_ms,
        )
        db.add(sr)

        await self._mark_completed(db, run)

    async def _build_cooccurrence(
        self, db, material_id: int, characters: list
    ) -> dict[tuple[int, int], list[int]]:
        """Build a co-occurrence map of character pairs → shared chapter indices."""
        from app.models.deepstudy import EntityMention

        char_ids = {c.id for c in characters}

        # Get all mentions for character entities
        mentions = (
            await db.execute(
                select(EntityMention).where(
                    EntityMention.material_id == material_id,
                    EntityMention.entity_id.in_(char_ids),
                )
            )
        ).scalars().all()

        # Map entity_id → set of chapter_indices
        entity_chapters: dict[int, set[int]] = {}
        for m in mentions:
            if m.entity_id not in entity_chapters:
                entity_chapters[m.entity_id] = set()
            # Get chapter_index from chapter relationship
            from app.models.study import StudyChapter
            chapter = await db.get(StudyChapter, m.chapter_id)
            if chapter:
                entity_chapters[m.entity_id].add(chapter.chapter_index)

        # Build pair co-occurrence
        pair_chapters: dict[tuple[int, int], list[int]] = {}
        char_list = list(entity_chapters.keys())
        for i in range(len(char_list)):
            for j in range(i + 1, len(char_list)):
                a, b = char_list[i], char_list[j]
                shared = entity_chapters[a] & entity_chapters[b]
                if len(shared) >= MIN_SHARED_CHAPTERS:
                    key = (min(a, b), max(a, b))
                    pair_chapters[key] = sorted(shared)

        return pair_chapters

    async def _get_shared_excerpt(
        self, db, material_id: int, chapter_indices: list[int]
    ) -> str:
        """Get concatenated text from shared chapters."""
        from app.models.study import StudyChapter

        chapters = (
            await db.execute(
                select(StudyChapter).where(
                    StudyChapter.material_id == material_id,
                    StudyChapter.chapter_index.in_(chapter_indices),
                ).order_by(StudyChapter.chapter_index)
            )
        ).scalars().all()

        parts = []
        total_len = 0
        for ch in chapters:
            content = ch.content or ""
            # Take first 1500 chars from each shared chapter
            excerpt = content[:1500]
            if excerpt:
                parts.append(f"【第{ch.chapter_index}章】\n{excerpt}")
                total_len += len(excerpt)
            if total_len >= 4000:
                break

        return "\n\n".join(parts)

    def _map_relation_type(self, relation: str) -> str:
        """Map Chinese relation label to spec enum."""
        mapping = {
            "师父": "master_disciple", "弟子": "master_disciple", "师徒": "master_disciple",
            "对手": "rival", "仇人": "enemy",
            "恋人": "lover", "夫妻": "lover",
            "朋友": "friend", "同门": "friend",
            "家人": "family", "兄弟": "family", "姐妹": "family",
            "父子": "family", "母子": "family",
            "主仆": "owner", "势力": "faction_member",
            "同盟": "ally", "合作": "ally",
            "敌人": "enemy",
        }
        return mapping.get(relation, "ally")

    async def _mark_completed(self, db, run) -> None:
        """Mark this stage as completed in run progress."""
        progress = dict(run.progress or {}) if isinstance(run.progress, dict) else {}
        completed = list(progress.get("completed_stages", []) or [])
        if self.stage_key not in completed:
            completed.append(self.stage_key)
        progress["completed_stages"] = completed
        progress["current_stage"] = self.stage_key
        run.progress = progress
        await db.commit()
