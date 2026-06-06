"""Chapter profiler stage — LLM-driven chapter analysis.

Replaces the old keyword-classification stub with real LLM calls
via PromptEngine + LLMRouter. Each chapter is analyzed independently
and the result is persisted to the ChapterAnalysis table.
"""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select

from .base import BaseStage
from .llm_helper import call_llm, safe_json_loads, truncate_text

logger = logging.getLogger(__name__)


class ChapterProfilerStage(BaseStage):
    stage_key = "chapter_profile"

    async def execute_chapter(
        self, db, run, chapter_index: int, chapter_text: str, prev_context=None
    ) -> dict:
        """Analyze a chapter with LLM and write ChapterAnalysis record."""
        from app.models.deepstudy import ChapterAnalysis
        from app.models.study import StudyChapter

        text = truncate_text(chapter_text, max_chars=8000) if chapter_text else ""

        if not text.strip():
            # Empty chapter — skip LLM call
            return {
                "summary": f"第{chapter_index}章（空章节）",
                "narrative_function": "空章节",
                "pov": "未知",
                "tone": "中性",
                "conflict_type": "无",
                "reader_hook": "",
                "pace_score": 0.0,
                "information_density": 0.0,
                "_input_tokens": 0,
                "_output_tokens": 0,
                "_cost_usd": 0.0,
                "_duration_ms": 0,
            }

        # Call LLM via the helper
        try:
            resolved, result = await call_llm(
                db,
                role="StudyAgent",
                prompt_key="study_chapter_profile",
                inputs={
                    "chapter_no": str(chapter_index),
                    "chapter_text": text,
                },
                temperature=0.0,
                max_tokens=2000,
                response_format={"type": "json_object"},
            )
            raw = result.content
            parsed = safe_json_loads(raw)
        except Exception as exc:
            logger.warning(f"ChapterProfiler LLM call failed for ch {chapter_index}: {exc}")
            parsed = None
            raw = ""
            result = None
            resolved = None

        # Build analysis from parsed or fallback
        if parsed and "summary" in parsed:
            analysis = {
                "summary": parsed.get("summary", ""),
                "narrative_function": parsed.get("narrative_function", "情节推进"),
                "pov": parsed.get("pov", "third_person"),
                "tone": parsed.get("tone", "中性"),
                "conflict_type": parsed.get("conflict_type", "内心挣扎"),
                "reader_hook": parsed.get("reader_hook", ""),
                "pace_score": float(parsed.get("pace_score", 0.5)),
                "information_density": float(parsed.get("information_density", 0.5)),
            }
        else:
            # Fallback: basic info from text
            analysis = {
                "summary": f"第{chapter_index}章（LLM 解析失败，使用摘要回退）",
                "narrative_function": "情节推进",
                "pov": "third_person",
                "tone": "中性",
                "conflict_type": "内心挣扎",
                "reader_hook": "",
                "pace_score": 0.5,
                "information_density": 0.5,
            }

        # Token/cost tracking
        if result is not None:
            analysis["_input_tokens"] = result.input_tokens or 0
            analysis["_output_tokens"] = result.output_tokens or 0
            analysis["_cost_usd"] = result.cost_usd or 0.0
            analysis["_duration_ms"] = result.duration_ms or 0
        else:
            analysis["_input_tokens"] = 0
            analysis["_output_tokens"] = 0
            analysis["_cost_usd"] = 0.0
            analysis["_duration_ms"] = 0

        # Persist to ChapterAnalysis
        chapter = (
            await db.execute(
                select(StudyChapter).where(
                    StudyChapter.material_id == run.material_id,
                    StudyChapter.chapter_index == chapter_index,
                )
            )
        ).scalar_one_or_none()

        if chapter is None:
            raise ValueError(f"Chapter {chapter_index} not found for material {run.material_id}")

        existing = await db.execute(
            select(ChapterAnalysis).where(
                ChapterAnalysis.run_id == run.id,
                ChapterAnalysis.chapter_index == chapter_index,
            )
        )
        ca = existing.scalar_one_or_none()
        if ca:
            ca.status = "succeeded"
            ca.summary = analysis["summary"]
            ca.narrative_function = analysis["narrative_function"]
            ca.pov = analysis["pov"]
            ca.tone = analysis["tone"]
            ca.conflict_type = analysis["conflict_type"]
            ca.reader_hook = analysis.get("reader_hook", "")
            ca.pace_score = analysis["pace_score"]
            ca.information_density = analysis["information_density"]
            ca.raw_result = parsed or {"raw_fallback": True}
        else:
            ca = ChapterAnalysis(
                run_id=run.id,
                material_id=run.material_id,
                chapter_id=chapter.id,
                chapter_index=chapter_index,
                status="succeeded",
                summary=analysis["summary"],
                narrative_function=analysis["narrative_function"],
                pov=analysis["pov"],
                tone=analysis["tone"],
                conflict_type=analysis["conflict_type"],
                reader_hook=analysis.get("reader_hook", ""),
                pace_score=analysis["pace_score"],
                information_density=analysis["information_density"],
                raw_result=parsed or {"raw_fallback": True},
            )
            db.add(ca)

        # Accumulate cost on the run
        run.input_tokens = (run.input_tokens or 0) + analysis["_input_tokens"]
        run.output_tokens = (run.output_tokens or 0) + analysis["_output_tokens"]
        run.cost_usd = round((run.cost_usd or 0.0) + analysis["_cost_usd"], 6)

        return analysis
