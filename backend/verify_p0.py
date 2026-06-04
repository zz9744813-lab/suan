"""P0 验收: 验证 P6 评论评审系统 seed 数据完整.
跑法: cd backend && python verify_p0.py
"""
import asyncio
import aiosqlite
import sys

from app.core.config import settings


async def main() -> int:
    db_path = settings.database_url.replace("sqlite+aiosqlite:///", "")
    failures: list[str] = []
    async with aiosqlite.connect(db_path) as db:
        def check(label: str, cond: bool, detail: str = "") -> None:
            mark = "PASS" if cond else "FAIL"
            print(f"  [{mark}] {label}{(': ' + detail) if detail else ''}")
            if not cond:
                failures.append(label)

        print("=== 1. 5 张新表都存在 ===")
        for t in [
            "reader_agent_profiles",
            "review_comments",
            "review_comment_groups",
            "reader_review_runs",
            "review_settings",
        ]:
            cur = await db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (t,)
            )
            row = await cur.fetchone()
            check(f"table {t} exists", row is not None)

        print("\n=== 2. AgentRole 17 行 (11 旧 + 6 新) ===")
        cur = await db.execute("SELECT key, category, run_mode FROM agent_roles ORDER BY id")
        rows = list(await cur.fetchall())
        check(f"agent_roles count = 17", len(rows) == 17, f"actual={len(rows)}")
        keys = {r[0] for r in rows}
        for k in ["reader_hook", "reader_emotion", "reader_logic",
                  "reader_commercial", "reader_toxic", "chief_comment_moderator"]:
            check(f"  role {k} exists", k in keys)

        print("\n=== 3. ReaderAgentProfile 5 行 ===")
        cur = await db.execute("SELECT reader_key, weight, enabled FROM reader_agent_profiles ORDER BY id")
        rows = list(await cur.fetchall())
        check(f"reader_agent_profiles count = 5", len(rows) == 5, f"actual={len(rows)}")
        for r in rows:
            check(f"  profile {r[0]} weight={r[1]} enabled={r[2]}", r[1] == 1.0 and r[2] == 1)

        print("\n=== 4. ReviewSettings 一行 per project ===")
        cur = await db.execute(
            "SELECT project_id, auto_reader_review, retention_days FROM review_settings ORDER BY project_id"
        )
        rows = list(await cur.fetchall())
        cur = await db.execute("SELECT id FROM projects ORDER BY id")
        project_ids = [r[0] for r in await cur.fetchall()]
        check(f"review_settings count = {len(project_ids)}", len(rows) == len(project_ids))
        for r in rows:
            check(f"  project {r[0]} auto={r[1]} retention={r[2]}", r[1] == 1 and r[2] == 7)

        print("\n=== 5. AgentModelBinding 17 行 (1:1 with AgentRole) ===")
        cur = await db.execute("SELECT agent_role_id FROM agent_model_bindings ORDER BY agent_role_id")
        rows = list(await cur.fetchall())
        check(f"agent_model_bindings count = 17", len(rows) == 17, f"actual={len(rows)}")
        role_ids = {r[0] for r in rows}
        cur = await db.execute("SELECT id FROM agent_roles")
        all_role_ids = {r[0] for r in await cur.fetchall()}
        check(f"  every agent_role has a binding", role_ids == all_role_ids)

        print("\n=== 6. WRITING_PROMPTS 23 行 (15 旧 + 8 新) ===")
        from app.prompts.default import WRITING_PROMPTS
        check(f"WRITING_PROMPTS count = 23", len(WRITING_PROMPTS) == 23, f"actual={len(WRITING_PROMPTS)}")
        for k in ["reader_hook_comment", "reader_emotion_comment", "reader_logic_comment",
                  "reader_commercial_comment", "reader_toxic_comment",
                  "chief_comment_triage", "chief_comment_reply", "chief_comment_decision"]:
            check(f"  prompt {k} exists", k in WRITING_PROMPTS)

        print("\n=== 7. 5 新 prompt 都写入 prompt_templates + prompt_versions ===")
        for k in ["reader_hook_comment", "reader_emotion_comment", "reader_logic_comment",
                  "reader_commercial_comment", "reader_toxic_comment",
                  "chief_comment_triage", "chief_comment_reply", "chief_comment_decision"]:
            cur = await db.execute(
                "SELECT id FROM prompt_templates WHERE template_key=?", (k,)
            )
            tpl = await cur.fetchone()
            check(f"  prompt_templates.{k}", tpl is not None)
            if tpl:
                cur = await db.execute(
                    "SELECT count(*) FROM prompt_versions WHERE template_id=? AND status='active'", (tpl[0],)
                )
                cnt = (await cur.fetchone())[0]
                check(f"    has active version", cnt == 1, f"active_versions={cnt}")

    print("\n" + "=" * 50)
    if failures:
        print(f"FAILED: {len(failures)} checks")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("ALL PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
