"""Chapter profiler stage - generates chapter summaries and analysis."""
from .base import BaseStage


class ChapterProfilerStage(BaseStage):
    stage_key = "chapter_profile"

    async def execute_chapter(self, db, run, chapter_index: int, chapter_text: str, prev_context=None):
        """Analyze a chapter and write ChapterAnalysis record."""
        from app.models.deepstudy import ChapterAnalysis
        from app.models.study import StudyChapter
        from sqlalchemy import select

        text_preview = chapter_text[:3000] if chapter_text else ""

        # For now: write a structured summary from text analysis
        # Full LLM integration will be added in Phase 2
        analysis = {
            "summary": f"Chapter {chapter_index} analysis",
            "narrative_function": self._classify_function(text_preview),
            "pov": "third_person",
            "tone": self._classify_tone(text_preview),
            "conflict_type": self._classify_conflict(text_preview),
            "reader_hook": "",
            "pace_score": 0.7,
            "information_density": 0.6,
            "_input_tokens": len(text_preview) // 3,
            "_output_tokens": 200,
            "_cost_usd": 0.001,
            "_duration_ms": 500,
        }

        # Look up chapter_id for FK
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

        # Write ChapterAnalysis
        existing = await db.execute(
            select(ChapterAnalysis).where(
                ChapterAnalysis.run_id == run.id,
                ChapterAnalysis.chapter_index == chapter_index,
            )
        )
        ca = existing.scalar_one_or_none()
        if not ca:
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
            )
            db.add(ca)

        return analysis

    def _classify_function(self, text: str) -> str:
        for kw, func in [
            ("羞辱", "身份压迫"),
            ("突破", "力量提升"),
            ("战斗", "冲突"),
            ("反转", "转折"),
            ("揭秘", "信息揭露"),
        ]:
            if kw in text:
                return func
        return "情节推进"

    def _classify_tone(self, text: str) -> str:
        for kw, tone in [
            ("怒", "激烈"),
            ("哭", "悲伤"),
            ("笑", "轻松"),
            ("沉默", "压抑"),
        ]:
            if kw in text:
                return tone
        return "中性"

    def _classify_conflict(self, text: str) -> str:
        for kw, ct in [
            ("羞辱", "身份压迫"),
            ("夺宝", "资源争夺"),
            ("背叛", "情感背叛"),
        ]:
            if kw in text:
                return ct
        return "内心挣扎"
