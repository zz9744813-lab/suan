"""Behavior pattern mine stage — LLM-driven behavior pattern extraction.

This stage operates at the book level. It:
1. Collects chapters with their extracted entities + scene beats.
2. Groups chapters into batches (to fit context window).
3. Calls StudyBehaviorPatternAgent to extract reusable behavior patterns.
4. Persists BehaviorPattern + BehaviorPatternEvidence rows.
"""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select

from .base import BaseStage
from .llm_helper import call_llm, safe_json_loads, truncate_text

logger = logging.getLogger(__name__)

# Max characters per batch for LLM input
BATCH_CHAR_LIMIT = 6000
# Max batches to process
MAX_BATCHES = 10


class BehaviorPatternMineStage(BaseStage):
    stage_key = "behavior_pattern_mine"

    async def execute_chapter(
        self, db, run, chapter_index: int, chapter_text: str, prev_context=None
    ) -> dict:
        """Not used — this stage operates at book level via execute_stage."""
        return {"skipped": True}

    async def execute_stage(self, db, run, stage_result_store) -> None:
        """Extract behavior patterns from extracted entities + events + scene beats."""
        from app.models.deepstudy import (
            BehaviorPatternEvidence,
            DeepStudyStageResult,
            Entity,
            SceneBeat,
        )
        from app.models.study import BehaviorPattern, StudyChapter

        material_id = run.material_id

        # 1. Load all chapters
        chapters = (
            await db.execute(
                select(StudyChapter).where(
                    StudyChapter.material_id == material_id
                ).order_by(StudyChapter.chapter_index)
            )
        ).scalars().all()

        if not chapters:
            await self._mark_completed(db, run)
            return

        # 2. Load entities and scene beats
        entities = (
            await db.execute(
                select(Entity).where(Entity.material_id == material_id)
            )
        ).scalars().all()

        scene_beats = (
            await db.execute(
                select(SceneBeat).where(SceneBeat.material_id == material_id)
            )
        ).scalars().all()

        # 3. Build evidence chunks — group chapters into batches
        batches = self._build_batches(chapters, entities, scene_beats)

        if not batches:
            await self._mark_completed(db, run)
            return

        # 4. Get existing patterns for dedup
        existing_patterns = await self._get_existing_patterns(db, material_id)

        # 5. Process each batch
        total_input_tokens = 0
        total_output_tokens = 0
        total_cost_usd = 0.0
        total_duration_ms = 0
        patterns_found = 0

        for batch_idx, batch_text in enumerate(batches[:MAX_BATCHES]):
            try:
                resolved, result = await call_llm(
                    db,
                    role="StudyAgent",
                    prompt_key="study_behavior_pattern",
                    inputs={
                        "evidence_chunks": batch_text,
                        "existing_patterns": existing_patterns or "暂无已识别模式",
                    },
                    temperature=0.0,
                    max_tokens=4000,
                    response_format={"type": "json_object"},
                )
                raw = result.content
                parsed = safe_json_loads(raw)
                total_input_tokens += result.input_tokens or 0
                total_output_tokens += result.output_tokens or 0
                total_cost_usd += result.cost_usd or 0.0
                total_duration_ms += result.duration_ms or 0
            except Exception as exc:
                logger.warning(f"BehaviorPattern LLM call failed for batch {batch_idx}: {exc}")
                parsed = None

            if not parsed or "patterns" not in parsed:
                continue

            for pat_data in parsed["patterns"]:
                if not isinstance(pat_data, dict):
                    continue
                name = pat_data.get("name", "").strip()
                if not name:
                    continue

                # Check for duplicate
                existing = (
                    await db.execute(
                        select(BehaviorPattern).where(
                            BehaviorPattern.source_material_id == material_id,
                            BehaviorPattern.name == name,
                        )
                    )
                ).scalar_one_or_none()

                if existing:
                    continue

                # Create BehaviorPattern
                pattern = BehaviorPattern(
                    source_material_id=material_id,
                    name=name,
                    character_tags=pat_data.get("character_tags", []),
                    situation_tags=pat_data.get("situation_tags", []),
                    typical_behavior=pat_data.get("typical_behavior", []),
                    dialogue_style=pat_data.get("dialogue_style", []),
                    scene_function=pat_data.get("scene_function", []),
                    risks=pat_data.get("risks", []),
                    recommended_plot_followup=pat_data.get("recommended_plot_followup", []),
                    confidence=0.7,
                )
                db.add(pattern)
                await db.flush()

                # Create evidence row
                evidence_quotes = pat_data.get("evidence", [])
                if isinstance(evidence_quotes, str):
                    evidence_quotes = [evidence_quotes]

                # Find a representative chapter
                first_chapter = chapters[0] if chapters else None
                if first_chapter is not None:
                    evidence = BehaviorPatternEvidence(
                        behavior_pattern_id=pattern.id,
                        material_id=material_id,
                        chapter_id=first_chapter.id,
                        situation=", ".join(pat_data.get("situation_tags", [])),
                        trigger=", ".join(pat_data.get("character_tags", [])),
                        behavior=", ".join(pat_data.get("typical_behavior", [])),
                        dialogue_style=", ".join(pat_data.get("dialogue_style", [])),
                        result="",
                        evidence_quote=evidence_quotes[0] if evidence_quotes else "",
                        confidence=0.7,
                    )
                    db.add(evidence)

                patterns_found += 1

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
                "patterns_found": patterns_found,
                "batches_processed": min(len(batches), MAX_BATCHES),
            },
            input_tokens=total_input_tokens,
            output_tokens=total_output_tokens,
            cost_usd=total_cost_usd,
            duration_ms=total_duration_ms,
        )
        db.add(sr)

        await self._mark_completed(db, run)

    def _build_batches(
        self, chapters, entities: list, scene_beats: list
    ) -> list[str]:
        """Group chapter texts with their entity/scene context into batches."""
        # Build lookup: chapter_index → scene beats
        beats_by_chapter: dict[int, list] = {}
        for beat in scene_beats:
            beats_by_chapter.setdefault(beat.chapter_index, []).append(beat)

        # Build character summary
        char_summary = "【已识别人物】\n"
        for e in entities:
            if e.entity_type == "character":
                role = (e.profile or {}).get("role", "")
                char_summary += f"- {e.name}"
                if role:
                    char_summary += f"（{role}）"
                char_summary += "\n"

        batches: list[str] = []
        current_batch = char_summary + "\n【章节片段】\n"
        current_len = len(current_batch)

        for ch in chapters:
            content = ch.content or ""
            excerpt = truncate_text(content, 3000)

            # Add scene beat summary if available
            beat_summary = ""
            for beat in beats_by_chapter.get(ch.chapter_index, []):
                beat_summary += f"  场景: {beat.title} ({beat.scene_type}) — {beat.summary}\n"

            chunk = f"\n--- 第{ch.chapter_index}章 ---\n{excerpt}\n"
            if beat_summary:
                chunk += f"场景节拍:\n{beat_summary}"

            if current_len + len(chunk) > BATCH_CHAR_LIMIT and current_len > len(char_summary) + 20:
                batches.append(current_batch)
                current_batch = char_summary + "\n【章节片段】\n"
                current_len = len(current_batch)

            current_batch += chunk
            current_len += len(chunk)

        if current_len > len(char_summary) + 20:
            batches.append(current_batch)

        return batches

    async def _get_existing_patterns(self, db, material_id: int) -> str:
        """Get existing pattern names for dedup."""
        patterns = (
            await db.execute(
                select(BehaviorPattern).where(
                    BehaviorPattern.source_material_id == material_id
                )
            )
        ).scalars().all()

        if not patterns:
            return ""
        return "\n".join(f"- {p.name}" for p in patterns[:20])

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
