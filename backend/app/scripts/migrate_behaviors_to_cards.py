"""Migrate old behavior_patterns into behavior_cards (B1 unified system).

Maps:
  old name                     → new name
  old character_tags (JSON[])  → BehaviorCardTag (tag_type="role")
  old situation_tags (JSON[])  → BehaviorCardTag (tag_type="scene")
  old typical_behavior (JSON[]) → new typical_behavior (Text, \\n-joined)
  old dialogue_style (JSON[])  → new dialogue_style (Text, \\n-joined)
  old confidence               → new fit_score
  old evidence (JSON[])        → BehaviorCardSource
  old source_material_id       → BehaviorCardSource.book_id
  old id                       → new source_pattern_id (FK backlink)
"""
import asyncio
import json

from sqlalchemy import select, text

from app.core.database import session_scope
from app.models.behavior_card import BehaviorCard, BehaviorCardSource, BehaviorCardTag


async def migrate():
    async with session_scope() as db:
        # ── 1. Query unmigrated behavior_patterns ──────────────────────
        result = await db.execute(text("""
            SELECT id, name, character_tags, situation_tags, typical_behavior,
                   dialogue_style, scene_function, risks,
                   recommended_plot_followup, confidence, evidence,
                   source_material_id, created_at
            FROM behavior_patterns
            WHERE id NOT IN (
                SELECT source_pattern_id FROM behavior_cards
                WHERE source_pattern_id IS NOT NULL
            )
        """))
        old_patterns = result.fetchall()

        if not old_patterns:
            print("No behavior_patterns to migrate.")
            return

        migrated = 0
        for p in old_patterns:
            pid = p[0]
            pname = p[1] or ""

            # ── Parse JSON fields safely ──────────────────────────────
            def _parse_json(val):
                if val is None:
                    return []
                if isinstance(val, str):
                    try:
                        return json.loads(val)
                    except (json.JSONDecodeError, TypeError):
                        return [val] if val.strip() else []
                if isinstance(val, list):
                    return val
                return []

            char_tags = _parse_json(p[2])   # character_tags
            sit_tags = _parse_json(p[3])    # situation_tags
            behavior = _parse_json(p[4])    # typical_behavior
            dialogue = _parse_json(p[5])    # dialogue_style
            evidence = _parse_json(p[10])   # evidence
            confidence = float(p[9]) if p[9] is not None else 0.5
            source_material_id = p[11]
            created_at = p[12]

            # ── Create BehaviorCard ──────────────────────────────────
            card = BehaviorCard(
                name=pname,
                source_pattern_id=pid,
                typical_behavior="\n".join(behavior) if behavior else None,
                dialogue_style="\n".join(dialogue) if dialogue else None,
                behavior_chain="\n".join(behavior) if behavior else None,
                fit_score=confidence,
                source_count=1,
                created_at=created_at,
            )
            db.add(card)
            await db.flush()  # get card.id

            # ── Create tags ──────────────────────────────────────────
            for tag_name in char_tags:
                if tag_name and str(tag_name).strip():
                    db.add(BehaviorCardTag(
                        card_id=card.id,
                        tag_type="role",
                        tag_name=str(tag_name).strip()[:80],
                    ))

            for tag_name in sit_tags:
                if tag_name and str(tag_name).strip():
                    db.add(BehaviorCardTag(
                        card_id=card.id,
                        tag_type="scene",
                        tag_name=str(tag_name).strip()[:80],
                    ))

            # ── Create sources (evidence) ────────────────────────────
            for ev in evidence[:5]:  # cap at 5
                if ev and str(ev).strip():
                    db.add(BehaviorCardSource(
                        card_id=card.id,
                        book_id=source_material_id,
                        source_type="book_analysis",
                        source_excerpt=str(ev).strip()[:2000],
                        confidence=confidence,
                    ))

            migrated += 1

        await db.commit()
        print(f"Migrated {migrated} old behavior patterns → behavior_cards")


asyncio.run(migrate())
