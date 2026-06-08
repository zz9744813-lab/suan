"""诊断脚本: 找出活库现有 material 的衍生物里, StudyDeleteService 实际漏掉的."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from app.core.database import AsyncSessionLocal  # noqa: E402
from sqlalchemy import text  # noqa: E402


async def main():
    async with AsyncSessionLocal() as session:
        rows = (await session.execute(text("SELECT id, title, study_status FROM study_materials ORDER BY id"))).all()
        print("Materials:", rows)
        for mid, title, status in rows:
            print(f"\n=== material id={mid} '{title}' study_status={status} ===")
            queries = [
                ("deepstudy_runs", f"SELECT COUNT(*) FROM deepstudy_runs WHERE material_id={mid}"),
                ("deepstudy_chapter_analyses", f"SELECT COUNT(*) FROM deepstudy_chapter_analyses WHERE material_id={mid}"),
                ("deepstudy_entities", f"SELECT COUNT(*) FROM deepstudy_entities WHERE material_id={mid}"),
                ("deepstudy_entity_mentions", f"SELECT COUNT(*) FROM deepstudy_entity_mentions WHERE material_id={mid}"),
                ("deepstudy_scene_beats", f"SELECT COUNT(*) FROM deepstudy_scene_beats WHERE material_id={mid}"),
                ("deepstudy_relationships", f"SELECT COUNT(*) FROM deepstudy_relationships WHERE material_id={mid}"),
                ("deepstudy_foreshadow_chains", f"SELECT COUNT(*) FROM deepstudy_foreshadow_chains WHERE material_id={mid}"),
                ("deepstudy_behavior_evidence", f"SELECT COUNT(*) FROM deepstudy_behavior_evidence WHERE material_id={mid}"),
                ("deepstudy_writing_techniques", f"SELECT COUNT(*) FROM deepstudy_writing_techniques WHERE material_id={mid}"),
                ("deepstudy_stage_results", f"SELECT COUNT(*) FROM deepstudy_stage_results WHERE material_id={mid}"),
                ("study_chapters", f"SELECT COUNT(*) FROM study_chapters WHERE material_id={mid}"),
                ("study_characters", f"SELECT COUNT(*) FROM study_characters WHERE material_id={mid}"),
                ("behavior_patterns", f"SELECT COUNT(*) FROM behavior_patterns WHERE source_material_id={mid}"),
                ("graph_nodes", f"SELECT COUNT(*) FROM graph_nodes WHERE source_material_id={mid}"),
                ("graph_edges (by node)", f"SELECT COUNT(*) FROM graph_edges e JOIN graph_nodes n ON e.source_node_id=n.id OR e.target_node_id=n.id WHERE n.source_material_id={mid}"),
                ("memory_foreshadows", f"SELECT COUNT(*) FROM memory_foreshadows WHERE source_material_id={mid}"),
            ]
            for name, q in queries:
                try:
                    n = (await session.execute(text(q))).scalar()
                except Exception as exc:
                    n = f"ERR {exc.__class__.__name__}: {str(exc)[:80]}"
                print(f"  {name}: {n}")


asyncio.run(main())
