import datetime
from app.core.database import session_scope
from sqlalchemy import select
from app.models.deepstudy import ForeshadowChain

SILENT_THRESHOLD_CHAPTERS = 50  # Warn if foreshadow is silent for 50+ chapters


async def check_silent_foreshadows(material_id: int, current_chapter_index: int) -> list[str]:
    """Find foreshadows that haven't been reinforced recently."""
    warnings = []
    async with session_scope() as db:
        result = await db.execute(
            select(ForeshadowChain).where(
                ForeshadowChain.material_id == material_id,
                ForeshadowChain.status.in_(["planted", "advanced"])
            )
        )
        chains = result.scalars().all()
        for chain in chains:
            last_chapter = max(chain.advanced_chapters or [chain.planted_chapter])
            silent = current_chapter_index - last_chapter
            if silent >= SILENT_THRESHOLD_CHAPTERS:
                warnings.append(
                    f"伏笔「{chain.name}」已沉默 {silent} 章 (第{last_chapter}→{current_chapter_index})，建议近期推进"
                )
    return warnings
