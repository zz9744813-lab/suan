"""项目资料上传后的 LLM 拆解与记忆写入服务。"""
from __future__ import annotations

import json
import re
import zipfile
from datetime import datetime
from io import BytesIO
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.sanitize import sanitize_for_storage, sanitize_text
from app.models.memory import MemoryCharacter, MemoryForeshadow, MemoryHardFact
from app.models.project import Project
from app.models.project_material import ProjectMaterial, ProjectMaterialIngestionRun
from app.services.llm.client import LLMClient, LLMMessage
from app.services.llm.router import LLMRouter

MATERIAL_TYPES = {
    "outline", "characters", "worldbuilding", "bible", "style", "constraints",
    "foreshadowing", "reader_promise", "other",
}


def extract_material_text(filename: str, data: bytes) -> str:
    lower = filename.lower()
    if lower.endswith(".docx"):
        return _extract_docx(data)
    text = _decode_text(data)
    return sanitize_text(text).strip()


def _decode_text(data: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "gb18030", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="ignore")


def _extract_docx(data: bytes) -> str:
    try:
        with zipfile.ZipFile(BytesIO(data)) as archive:
            xml = archive.read("word/document.xml").decode("utf-8", errors="ignore")
        xml = re.sub(r"</w:p>", "\n", xml)
        xml = re.sub(r"<[^>]+>", "", xml)
        return sanitize_text(xml).strip()
    except Exception:
        return _decode_text(data)


def count_words_rough(text: str) -> int:
    return len(re.findall(r"[\u4e00-\u9fff]|[A-Za-z0-9_]+", text or ""))


class ProjectMaterialIngestionService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.router = LLMRouter(LLMClient())

    async def ingest(self, material: ProjectMaterial) -> ProjectMaterialIngestionRun:
        project = await self.db.get(Project, material.project_id)
        run = ProjectMaterialIngestionRun(
            project_id=material.project_id,
            material_id=material.id,
            status="running",
        )
        self.db.add(run)
        await self.db.flush()
        try:
            result = await self._llm_decompose(project, material)
            if not result:
                result = self._rule_decompose(material)
            result = sanitize_for_storage(result)
            created_counts = await self._write_memories(material.project_id, material.id, result)
            run.status = "succeeded"
            run.result = result
            run.summary = result.get("summary") or f"已拆解资料《{material.title}》并写入项目记忆。"
            run.created_counts = created_counts
            run.finished_at = datetime.utcnow()
            material.status = "ingested"
            material.ingest_summary = run.summary
            material.ingest_result = result
            await self.db.flush()
            return run
        except Exception as exc:
            run.status = "failed"
            run.error_message = sanitize_text(str(exc))
            run.finished_at = datetime.utcnow()
            material.status = "failed"
            await self.db.flush()
            return run

    async def _llm_decompose(self, project: Project | None, material: ProjectMaterial) -> dict[str, Any] | None:
        text = (material.extracted_text or "")[:12000]
        if not text.strip():
            return None
        prompt = f"""
你是小说项目资料拆解 Agent。请把上传资料拆解成项目记忆，必须输出 JSON，不要输出解释。
项目名：{getattr(project, 'name', '')}
题材：{getattr(project, 'genre', '')}
简介：{getattr(project, 'description', '')}
资料类型：{material.material_type}
资料标题：{material.title}

输出 JSON 格式：
{{
  "summary": "资料总体说明",
  "characters": [{{"name":"人物名","role":"protagonist/support/villain/heroine","aliases":[],"tags":[],"profile":{{"说明":"..."}}}}],
  "foreshadows": [{{"name":"伏笔名","summary":"说明","importance":0.5,"related_characters":[],"related_items":[],"related_main_plot":""}}],
  "hard_facts": [{{"category":"world_rule/style/constraint/outline/setting","fact":"必须遵守的稳定事实"}}],
  "notes": ["需要人工确认或冲突点"]
}}

资料正文：
{text}
""".strip()
        try:
            _, response = await self.router.chat(
                self.db,
                "memory",
                [LLMMessage(role="user", content=prompt)],
                temperature=0.2,
                max_tokens=2500,
                response_format={"type": "json_object"},
                stream=False,
                project_id=material.project_id,
                step_key="project_material_ingestion",
                task_type="project_material_ingestion",
            )
            return _parse_json_object(response.content)
        except Exception:
            return None

    def _rule_decompose(self, material: ProjectMaterial) -> dict[str, Any]:
        text = material.extracted_text or ""
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        facts: list[dict[str, str]] = []
        category = {
            "style": "style",
            "constraints": "constraint",
            "outline": "outline",
            "worldbuilding": "world_rule",
            "bible": "setting",
        }.get(material.material_type, "setting")
        for line in lines[:30]:
            if len(line) >= 8:
                facts.append({"category": category, "fact": line[:1200]})
        return {
            "summary": f"规则兜底拆解：从《{material.title}》提取 {len(facts)} 条项目记忆。",
            "characters": [],
            "foreshadows": [],
            "hard_facts": facts,
            "notes": ["LLM 拆解不可用时使用规则兜底，建议人工复核。"],
        }

    async def _write_memories(self, project_id: int, material_id: int, result: dict[str, Any]) -> dict[str, int]:
        counts = {"characters": 0, "foreshadows": 0, "hard_facts": 0}
        for item in result.get("characters") or []:
            name = str(item.get("name") or "").strip()
            if not name:
                continue
            existing = (await self.db.execute(
                select(MemoryCharacter).where(MemoryCharacter.project_id == project_id, MemoryCharacter.name == name).limit(1)
            )).scalar_one_or_none()
            if existing:
                profile = dict(existing.base_profile or {})
                profile.setdefault("资料拆解说明", item.get("profile") or item.get("summary") or "")
                existing.base_profile = profile
            else:
                self.db.add(MemoryCharacter(
                    project_id=project_id,
                    name=name[:120],
                    aliases=item.get("aliases") or [],
                    role=str(item.get("role") or "support")[:40],
                    tags=item.get("tags") or ["资料拆解"],
                    base_profile={"来源": "半自动资料上传", "source_material_id": material_id, "profile": item.get("profile") or {}},
                ))
                counts["characters"] += 1
        for item in result.get("foreshadows") or []:
            name = str(item.get("name") or "").strip()
            if not name:
                continue
            self.db.add(MemoryForeshadow(
                project_id=project_id,
                name=name[:200],
                summary=str(item.get("summary") or "")[:2000],
                importance=float(item.get("importance") or 0.5),
                related_characters=item.get("related_characters") or [],
                related_items=item.get("related_items") or [],
                related_main_plot=item.get("related_main_plot") or None,
            ))
            counts["foreshadows"] += 1
        for item in result.get("hard_facts") or []:
            fact = str(item.get("fact") or "").strip()
            if not fact:
                continue
            self.db.add(MemoryHardFact(
                project_id=project_id,
                category=str(item.get("category") or "setting")[:40],
                fact=f"[资料#{material_id}] {fact}"[:2000],
            ))
            counts["hard_facts"] += 1
        await self.db.flush()
        return counts


def _parse_json_object(text: str) -> dict[str, Any] | None:
    if not text:
        return None
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return None
        try:
            value = json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            return None
    return value if isinstance(value, dict) else None
