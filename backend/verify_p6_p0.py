"""P6 P0 验证脚本: 5 张新表 + 6 新 AgentRole + 5 ReaderAgentProfile + ReviewSettings"""
import asyncio
import aiosqlite
from app.core.config import settings


async def main():
    db_path = settings.database_url.replace("sqlite+aiosqlite:///", "")
    async with aiosqlite.connect(db_path) as db:
        # 1. 5 张新表存在
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
            mark = "OK" if row else "MISSING"
            print(f"  table {t}: {mark}")

        # 2. AgentRole 总数 (应 = 17)
        cur = await db.execute("SELECT COUNT(*) FROM agent_roles")
        n = (await cur.fetchone())[0]
        print(f"  agent_roles 行数: {n} (期望 17)")

        # 3. 6 个新角色
        cur = await db.execute(
            "SELECT key, category, run_mode, pipeline_stage FROM agent_roles "
            "WHERE key IN ('reader_hook','reader_emotion','reader_logic',"
            "'reader_commercial','reader_toxic','chief_comment_moderator')"
        )
        print("  6 个新角色:")
        for r in await cur.fetchall():
            print(f"    {r}")

        # 4. ReaderAgentProfile (5 个)
        cur = await db.execute(
            "SELECT reader_key, display_name, dimension, weight, enabled "
            "FROM reader_agent_profiles"
        )
        rows = list(await cur.fetchall())
        print(f"  reader_agent_profiles 行数: {len(rows)} (期望 5)")
        for r in rows:
            print(f"    {r}")

        # 5. ReviewSettings (per project)
        cur = await db.execute("SELECT project_id, retention_days, max_comments_per_chapter FROM review_settings")
        rows = list(await cur.fetchall())
        print(f"  review_settings 行数: {len(rows)} (期望 ≥ 1)")

        # 6. 8 个新 prompt
        cur = await db.execute(
            "SELECT template_key, category, role FROM prompt_templates "
            "WHERE template_key LIKE 'reader_%' OR template_key LIKE 'chief_comment_%' "
            "ORDER BY template_key"
        )
        rows = list(await cur.fetchall())
        print(f"  新 prompt 模板数: {len(rows)} (期望 8)")
        for r in rows:
            print(f"    {r}")

        # 7. AgentModelBinding (应有 17)
        cur = await db.execute("SELECT COUNT(*) FROM agent_model_bindings")
        n = (await cur.fetchone())[0]
        print(f"  agent_model_bindings 行数: {n} (期望 17)")


asyncio.run(main())
