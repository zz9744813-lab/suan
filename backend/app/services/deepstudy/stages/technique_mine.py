"""Technique mine stage — LLM-driven writing technique extraction.

This stage operates at the book level. It:
1. Collects extracted behavior patterns, scene beats, and foreshadow chains.
2. Groups them by recurring situations / technique types.
3. Calls LLM to distil reusable writing techniques with prompt_hint
   and anti_pattern.
4. Persists WritingTechnique rows.
"""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select

from .base import BaseStage
from .llm_helper import call_llm, safe_json_loads, truncate_text

logger = logging.getLogger(__name__)


class TechniqueMineStage(BaseStage):
    stage_key = "technique_mine"

    async def execute_chapter(
        self, db, run, chapter_index: int, chapter_text: str, prev_context=None
    ) -> dict:
        """Not used — this stage operates at book level via execute_stage."""
        return {"skipped": True}

    async def execute_stage(self, db, run, stage_result_store) -> None:
        """Extract writing techniques from behavior patterns + scene beats + foreshadows."""
        from app.models.deepstudy import (
            DeepStudyStageResult,
            ForeshadowChain,
            SceneBeat,
            WritingTechnique,
        )
        from app.models.study import BehaviorPattern

        material_id = run.material_id

        # 1. Load all source data
        patterns = (
            await db.execute(
                select(BehaviorPattern).where(
                    BehaviorPattern.source_material_id == material_id
                )
            )
        ).scalars().all()

        scene_beats = (
            await db.execute(
                select(SceneBeat).where(SceneBeat.material_id == material_id)
            )
        ).scalars().all()

        foreshadows = (
            await db.execute(
                select(ForeshadowChain).where(
                    ForeshadowChain.material_id == material_id
                )
            )
        ).scalars().all()

        if not patterns and not scene_beats and not foreshadows:
            await self._mark_completed(db, run)
            return

        # 2. Build evidence summary for LLM
        evidence_text = self._build_evidence_text(patterns, scene_beats, foreshadows)

        # 3. Call LLM
        total_input_tokens = 0
        total_output_tokens = 0
        total_cost_usd = 0.0
        total_duration_ms = 0
        techniques_found = 0

        try:
            resolved, result = await call_llm(
                db,
                role="StudyAgent",
                prompt_key="study_technique_mine",
                inputs={
                    "evidence_summary": truncate_text(evidence_text, 8000),
                    "book_title": "",  # Optional
                },
                temperature=0.0,
                max_tokens=4000,
                response_format={"type": "json_object"},
            )
            raw = result.content
            parsed = safe_json_loads(raw)
            total_input_tokens = result.input_tokens or 0
            total_output_tokens = result.output_tokens or 0
            total_cost_usd = result.cost_usd or 0.0
            total_duration_ms = result.duration_ms or 0
        except Exception as exc:
            logger.warning(f"TechniqueMine LLM call failed: {exc}")
            parsed = None

        if parsed and "techniques" in parsed:
            for tech_data in parsed["techniques"]:
                if not isinstance(tech_data, dict):
                    continue
                name = tech_data.get("name", "").strip()
                if not name:
                    continue

                # Check for duplicate
                existing = (
                    await db.execute(
                        select(WritingTechnique).where(
                            WritingTechnique.material_id == material_id,
                            WritingTechnique.name == name,
                        )
                    )
                ).scalar_one_or_none()

                if existing:
                    continue

                technique = WritingTechnique(
                    material_id=material_id,
                    name=name,
                    technique_type=tech_data.get("technique_type", "其他"),
                    summary=tech_data.get("summary", ""),
                    applicable_genres=tech_data.get("applicable_genres", []),
                    applicable_situations=tech_data.get("applicable_situations", []),
                    source_entity_ids=[],
                    source_scene_ids=[sb.id for sb in scene_beats[:5]],
                    source_behavior_ids=[p.id for p in patterns[:5]],
                    evidence_quotes=tech_data.get("evidence_quotes", []),
                    prompt_hint=tech_data.get("prompt_hint", ""),
                    anti_pattern=tech_data.get("anti_pattern"),
                    confidence=float(tech_data.get("confidence", 0.5)),
                )
                db.add(technique)
                techniques_found += 1

        # If LLM failed or returned nothing, try to create techniques from patterns
        if techniques_found == 0 and patterns:
            techniques_found = await self._fallback_techniques_from_patterns(
                db, material_id, patterns
            )

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
            output_json={"techniques_found": techniques_found},
            input_tokens=total_input_tokens,
            output_tokens=total_output_tokens,
            cost_usd=total_cost_usd,
            duration_ms=total_duration_ms,
        )
        db.add(sr)

        await self._mark_completed(db, run)

    def _build_evidence_text(
        self, patterns, scene_beats, foreshadows
    ) -> str:
        """Build a text summary of all source data for the LLM prompt."""
        parts = []

        if patterns:
            parts.append("【行为模式】")
            for p in patterns[:15]:
                char_tags = "、".join(p.character_tags or [])
                sit_tags = "、".join(p.situation_tags or [])
                behavior = "；".join(p.typical_behavior or [])
                parts.append(
                    f"- {p.name}（人物:{char_tags} | 情境:{sit_tags}）\n"
                    f"  行为: {behavior}"
                )

        if scene_beats:
            parts.append("\n【关键场景节拍】")
            # Pick the most important beats
            important_beats = sorted(scene_beats, key=lambda b: b.importance, reverse=True)[:15]
            for sb in important_beats:
                parts.append(
                    f"- 第{sb.chapter_index}章 · {sb.title} ({sb.scene_type})\n"
                    f"  触发: {sb.trigger or ''} → 行动: {sb.action or ''} → 结果: {sb.result or ''}"
                )

        if foreshadows:
            parts.append("\n【伏笔链】")
            for fc in foreshadows[:10]:
                parts.append(
                    f"- {fc.name} ({fc.foreshadow_type})\n"
                    f"  埋设: 第{fc.planted_chapter}章 → 回收: 第{fc.payoff_chapter}章\n"
                    f"  {fc.summary}"
                )

        return "\n".join(parts)

    async def _fallback_techniques_from_patterns(
        self, db, material_id: int, patterns
    ) -> int:
        """When LLM fails, create basic techniques from pattern data."""
        count = 0
        for p in patterns[:10]:
            name = f"{p.name}写作法"
            existing = (
                await db.execute(
                    select(WritingTechnique).where(
                        WritingTechnique.material_id == material_id,
                        WritingTechnique.name == name,
                    )
                )
            ).scalar_one_or_none()

            if existing:
                continue

            sit_tags = "、".join(p.situation_tags or [])
            behavior = "；".join(p.typical_behavior or [])

            tech = WritingTechnique(
                material_id=material_id,
                name=name,
                technique_type="人物塑造",
                summary=f"当遇到「{sit_tags}」情境时，角色通常表现为「{behavior}」",
                applicable_situations=p.situation_tags or [],
                source_behavior_ids=[p.id],
                prompt_hint=f"写{sit_tags}场景时，角色可表现出：{behavior}",
                confidence=0.4,
            )
            db.add(tech)
            count += 1

        return count

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
