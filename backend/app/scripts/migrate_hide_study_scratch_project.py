"""P0 修复: 把现有的"拆书·公共" / 任何遗留系统占位项目打系统标记。

不要删 — 历史 DeepStudy run / AgentTask 可能引用它们的 project_id。
只隐藏 + 改 description, 物理保留。
"""
import asyncio
import logging

from sqlalchemy import select

from app.core.database import session_scope
from app.models.project import Project

logging.disable(logging.CRITICAL)


async def main() -> None:
    async with session_scope() as db:
        # 既要兼容旧中文名, 也要兜底未来系统名
        target_names = ["拆书·公共", "__NF2_SYSTEM_DEEPSTUDY__"]
        rows = (await db.execute(
            select(Project).where(Project.name.in_(target_names))
        )).scalars().all()
        if not rows:
            print("  没找到需要迁移的系统项目。")
            return
        for p in rows:
            p.genre = "system"
            p.category = "__system_deepstudy"
            p.status = "system"
            if not (p.description or "").strip():
                p.description = "系统内部项目：承载未绑定正式项目的 DeepStudy 任务，不在项目书架展示。"
            print(f"  标记 #{p.id} name={p.name!r} -> system/{p.category}")
        print(f"  共 {len(rows)} 行已标 system。")


if __name__ == "__main__":
    asyncio.run(main())
