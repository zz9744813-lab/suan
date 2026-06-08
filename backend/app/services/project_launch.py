"""ProjectLaunchService — 双模式创作启动器。

模式一 (semi_auto): 用户提供大纲/人物/设定文本 → 系统自动创建 → 启动写作管线
模式二 (full_auto): 系统全自动 → LLM 生成大纲/人物/设定 → 启动写作管线
"""
from __future__ import annotations

import json
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import Bible, Chapter, Outline, Project
from app.models.task import AgentTask, WorkerPolicy
from app.services.llm.router import LLMRouter
from app.services.prompt_engine import PromptEngine


class ProjectLaunchService:
    """Launch a project into active writing with one of two modes."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ------------------------------------------------------------------
    #  Mode 1: Semi-Auto (用户提供素材)
    # ------------------------------------------------------------------
    async def launch_semi_auto(
        self,
        project_id: int,
        *,
        outline_text: str | None = None,
        character_text: str | None = None,
        bible_text: str | None = None,
    ) -> dict[str, Any]:
        """用户提供了大纲/人物/设定文本，系统自动创建并启动写作。"""
        project = await self.db.get(Project, project_id)
        if not project:
            raise ValueError(f"Project {project_id} not found")

        results: dict[str, Any] = {
            "mode": "semi_auto",
            "outlines_created": 0,
            "characters_created": 0,
            "bible_updated": False,
            "first_task_id": None,
        }

        # 1. 解析并创建大纲
        if outline_text and outline_text.strip():
            outlines = self._parse_outline_text(outline_text, project_id)
            for o in outlines:
                self.db.add(o)
            await self.db.flush()
            results["outlines_created"] = len(outlines)

        # 2. 解析并创建人物
        if character_text and character_text.strip():
            from app.models.memory import MemoryCharacter
            characters = self._parse_character_text(character_text, project_id)
            for c in characters:
                self.db.add(c)
            await self.db.flush()
            results["characters_created"] = len(characters)

        # 3. 更新 Bible (设定)
        if bible_text and bible_text.strip():
            bible = (
                await self.db.execute(
                    select(Bible).where(
                        Bible.project_id == project_id, Bible.is_active.is_(True)
                    )
                )
            ).scalar_one_or_none()
            if bible:
                bible.content = {
                    "world": bible_text.strip(),
                    "protagonist": bible.content.get("protagonist", "（待设定）"),
                }
                bible.version += 1
                results["bible_updated"] = True

        await self.db.flush()

        # 4. 从第一个大纲创建章节并启动管线
        first_outline = (
            await self.db.execute(
                select(Outline)
                .where(Outline.project_id == project_id)
                .order_by(Outline.chapter_no.asc())
                .limit(1)
            )
        ).scalar_one_or_none()

        if first_outline:
            chapter = Chapter(
                project_id=project_id,
                outline_id=first_outline.id,
                chapter_no=first_outline.chapter_no,
                title=first_outline.title,
                target_word_count=first_outline.target_word_count,
                status="queued",
            )
            self.db.add(chapter)
            await self.db.flush()

            task = AgentTask(
                project_id=project_id,
                chapter_id=chapter.id,
                task_type="chapter_pipeline",
                status="pending",
                priority=100,
                domain="writing",
                payload={"mode": "full", "auto_launched": True},
                display_title=f"写作: 第{chapter.chapter_no}章 {chapter.title}",
            )
            self.db.add(task)
            await self.db.flush()
            results["first_task_id"] = task.id
            results["first_chapter_id"] = chapter.id
            results["first_task_type"] = "chapter_pipeline"

        return results

    # ------------------------------------------------------------------
    #  Mode 2: Full-Auto (LLM 生成一切)
    # ------------------------------------------------------------------
    async def launch_full_auto(self, project_id: int) -> dict[str, Any]:
        """全自动模式：创建 bootstrap 任务，由 Worker 调用 LLM 生成大纲/人物/设定。"""
        project = await self.db.get(Project, project_id)
        if not project:
            raise ValueError(f"Project {project_id} not found")

        # 创建 project_bootstrap 任务
        task = AgentTask(
            project_id=project_id,
            task_type="project_bootstrap",
            status="pending",
            priority=200,  # 高优先级，Worker 先处理
            domain="writing",
            payload={
                "mode": "full_auto",
                "project_name": project.name,
                "genre": project.genre,
                "target_chapter_count": project.target_chapter_count,
                "description": project.description or "",
            },
            display_title=f"全自动启动: {project.name}",
        )
        self.db.add(task)
        await self.db.flush()

        return {
            "mode": "full_auto",
            "bootstrap_task_id": task.id,
            "first_task_id": task.id,
            "first_task_type": "project_bootstrap",
            "message": "已创建全自动启动任务，Worker 将自动生成大纲、人物、设定并开始写作。",
        }

    # ------------------------------------------------------------------
    #  Outline text parser
    # ------------------------------------------------------------------
    @staticmethod
    def _parse_outline_text(text: str, project_id: int) -> list[Outline]:
        """解析用户输入的大纲文本，支持多种格式：
        - 每行一条: `章节号|标题|简介|重要性`
        - 每行一条: `章节号 标题` (空格分隔)
        - 纯标题列表 (自动编号)
        - JSON 数组格式
        """
        lines = [l.strip() for l in text.strip().splitlines() if l.strip()]
        outlines: list[Outline] = []

        # 尝试 JSON 格式
        if text.strip().startswith("["):
            try:
                items = json.loads(text.strip())
                for item in items:
                    if isinstance(item, dict):
                        outlines.append(Outline(
                            project_id=project_id,
                            chapter_no=int(item.get("chapter_no", len(outlines) + 1)),
                            title=str(item.get("title", f"第{len(outlines)+1}章")),
                            summary=item.get("summary"),
                            importance=int(item.get("importance", 50)),
                            target_word_count=int(item.get("target_word_count", 3000)),
                        ))
                    elif isinstance(item, str):
                        outlines.append(Outline(
                            project_id=project_id,
                            chapter_no=len(outlines) + 1,
                            title=item,
                            target_word_count=3000,
                        ))
                return outlines
            except (json.JSONDecodeError, ValueError):
                pass

        # 管道符分隔格式
        for line in lines:
            if "|" in line:
                parts = [p.strip() for p in line.split("|")]
                chapter_no = int(parts[0]) if parts[0].isdigit() else len(outlines) + 1
                title = parts[1] if len(parts) > 1 else f"第{chapter_no}章"
                summary = parts[2] if len(parts) > 2 else None
                importance = int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else 50
                outlines.append(Outline(
                    project_id=project_id,
                    chapter_no=chapter_no,
                    title=title,
                    summary=summary,
                    importance=importance,
                    target_word_count=3000,
                ))
            else:
                # 纯文本行，尝试提取章节号
                match = re.match(r"^(\d+)[\.\s、]+(.+)$", line)
                if match:
                    chapter_no = int(match.group(1))
                    title = match.group(2).strip()
                else:
                    chapter_no = len(outlines) + 1
                    title = line
                outlines.append(Outline(
                    project_id=project_id,
                    chapter_no=chapter_no,
                    title=title,
                    target_word_count=3000,
                ))

        return outlines

    # ------------------------------------------------------------------
    #  Character text parser
    # ------------------------------------------------------------------
    @staticmethod
    def _parse_character_text(text: str, project_id: int) -> list:
        """解析用户输入的人物文本，支持格式：
        - 每行一个人物: `名字|角色|简介`
        - JSON 数组格式
        """
        from app.models.memory import MemoryCharacter
        lines = [l.strip() for l in text.strip().splitlines() if l.strip()]
        characters: list[MemoryCharacter] = []

        # 尝试 JSON 格式
        if text.strip().startswith("["):
            try:
                items = json.loads(text.strip())
                for item in items:
                    if isinstance(item, dict):
                        characters.append(MemoryCharacter(
                            project_id=project_id,
                            name=str(item.get("name", "未命名")),
                            role=item.get("role", "supporting"),
                            base_profile=item.get("profile", {}),
                            tags=item.get("tags", []),
                        ))
                    elif isinstance(item, str):
                        characters.append(MemoryCharacter(
                            project_id=project_id,
                            name=item,
                            role="supporting",
                        ))
                return characters
            except (json.JSONDecodeError, ValueError):
                pass

        # 管道符/逗号分隔
        for line in lines:
            if "|" in line:
                parts = [p.strip() for p in line.split("|")]
                name = parts[0]
                role = parts[1] if len(parts) > 1 else "supporting"
                profile_text = parts[2] if len(parts) > 2 else ""
                characters.append(MemoryCharacter(
                    project_id=project_id,
                    name=name,
                    role=role,
                    base_profile={"description": profile_text} if profile_text else {},
                ))
            else:
                characters.append(MemoryCharacter(
                    project_id=project_id,
                    name=line,
                    role="supporting",
                ))

        return characters
