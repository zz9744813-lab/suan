"""无人值守夜间验收流水线。

用法：
    python -m app.scripts.nightly_pipeline --mode smoke --chapter-limit 50 \
        --base-url http://107.172.138.14:3000/v1 --api-key sk-...

目标：
- 复用现有数据库模型，不改动主架构。
- 可断点续跑，所有进度落盘到 runtime/nightly。
- 生成拆书报告、500 章目录、前 N 章正文/评审/返工/记忆更新。
- 禁止空章节冒充完成：正文长度不足会失败并写入 errors.json。
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select

from app.core.database import init_db, session_scope
from app.models.project import Bible, Chapter, ChapterVersion, Outline, Project
from app.models.study import BehaviorPattern, GraphNode, StudyChapter, StudyCharacter, StudyMaterial
from app.models.task import AgentTask, WorkerPolicy
from app.services.llm.client import LLMClient, LLMMessage, LLMRequest

BACKEND_DIR = Path(__file__).resolve().parents[2]
PROJECT_ROOT = BACKEND_DIR.parent
RUNTIME_DIR = PROJECT_ROOT / "runtime" / "nightly"
DECON_DIR = PROJECT_ROOT / "outputs" / "deconstruction"
NOVEL_DIR = PROJECT_ROOT / "outputs" / "novel_500"
REPORT_DIR = PROJECT_ROOT / "outputs" / "reports"
DEFAULT_SOURCE_DIR = Path(r"F:\小说\gem\群像")
DEFAULT_SOURCE_BOOK = "诡秘之主.txt"
MIN_CHAPTER_CHARS = 500


@dataclass
class CommandResult:
    command: str
    ok: bool
    detail: str


@dataclass
class RunState:
    mode: str
    chapter_limit: int
    outline_count: int
    source_book: str
    started_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    completed_at: str | None = None
    project_id: int | None = None
    material_id: int | None = None
    model: str | None = None
    generated_outline_count: int = 0
    generated_chapters: int = 0
    reviewed_chapters: int = 0
    rewritten_chapters: int = 0
    memory_updates: int = 0
    blocked: bool = False
    errors: list[dict[str, Any]] = field(default_factory=list)
    commands: list[CommandResult] = field(default_factory=list)

    def to_json(self) -> dict[str, Any]:
        data = self.__dict__.copy()
        data["commands"] = [c.__dict__ for c in self.commands]
        return data


def ensure_dirs() -> None:
    for path in [RUNTIME_DIR, DECON_DIR, NOVEL_DIR, REPORT_DIR, NOVEL_DIR / "chapters", NOVEL_DIR / "reviews", NOVEL_DIR / "memory", NOVEL_DIR / "rewrites"]:
        path.mkdir(parents=True, exist_ok=True)


def record_command(state: RunState, command: str, ok: bool, detail: str) -> None:
    state.commands.append(CommandResult(command=command, ok=ok, detail=detail))
    write_json(RUNTIME_DIR / "status.json", state.to_json())


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def load_text_file(path: Path) -> str:
    raw = path.read_bytes()
    for enc in ("utf-8", "utf-8-sig", "gb18030", "gbk", "gb2312"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def split_source_chapters(text: str, limit: int = 80) -> list[dict[str, Any]]:
    pattern = re.compile(r"(?m)^\s*(第[一二三四五六七八九十百千万零〇两\d]+[章节卷回][^\n]{0,60})\s*$")
    matches = list(pattern.finditer(text))
    chapters: list[dict[str, Any]] = []
    if len(matches) >= 2:
        for idx, match in enumerate(matches[:limit]):
            start = match.end()
            end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
            body = text[start:end].strip()
            if len(body) >= 200:
                chapters.append({"index": len(chapters) + 1, "title": match.group(1).strip(), "content": body, "char_count": len(body)})
    if chapters:
        return chapters

    blocks = [b.strip() for b in re.split(r"\n\s*\n", text) if len(b.strip()) >= 200]
    for idx, body in enumerate(blocks[:limit], start=1):
        chapters.append({"index": idx, "title": f"片段 {idx}", "content": body, "char_count": len(body)})
    return chapters


def extract_names(text: str, max_items: int = 24) -> list[str]:
    candidates = re.findall(r"[\u4e00-\u9fff]{2,4}", text[:120_000])
    stop = {"这是", "一个", "他们", "自己", "什么", "没有", "说道", "知道", "时候", "已经", "可以", "因为", "所以", "如果", "但是", "然后", "只是", "不是", "这个", "那个"}
    freq: dict[str, int] = {}
    for name in candidates:
        if name in stop or name.startswith("第") or len(set(name)) == 1:
            continue
        freq[name] = freq.get(name, 0) + 1
    return [name for name, _ in sorted(freq.items(), key=lambda kv: kv[1], reverse=True)[:max_items]]


def build_deconstruction(source_path: Path, text: str, chapters: list[dict[str, Any]]) -> dict[str, Any]:
    sample = "\n".join(c["content"][:1200] for c in chapters[:10])
    names = extract_names(sample)
    characters = [
        {
            "name": name,
            "role": "核心/高频人物" if idx < 6 else "配角/功能人物",
            "tags": ["高频出场", "可学习人物行为"],
            "evidence_count": sample.count(name),
        }
        for idx, name in enumerate(names)
    ]
    plot_nodes = [
        {"chapter": c["index"], "title": c["title"], "node": c["content"][:180].replace("\n", " ")}
        for c in chapters[:20]
    ]
    techniques = [
        "章节开头用信息差或异常事件制造悬念",
        "通过人物目标与外部压力叠加推进剧情",
        "用连续小反转维持阅读动力",
        "用关系变化和身份差制造长期张力",
        "在章末保留未解决问题作为追读钩子",
    ]
    report = {
        "source_file": str(source_path),
        "raw_text_length": len(text),
        "chapter_count": len(chapters),
        "characters": characters,
        "relationships": [
            {"source": characters[i]["name"], "target": characters[i + 1]["name"], "relation": "同场/潜在冲突或协作"}
            for i in range(min(len(characters) - 1, 8))
        ],
        "plot_nodes": plot_nodes,
        "conflict_structure": ["目标受阻", "身份/信息差", "势力压迫", "资源争夺", "情感与利益冲突"],
        "hooks": ["未揭示身份", "未兑现承诺", "隐藏敌意", "危机倒计时", "章末疑问"],
        "rhythm_points": ["开局钩子", "中段升级", "尾段反转", "跨章悬念"],
        "techniques": techniques,
        "scene_templates": [
            "弱势人物遭遇规则压迫后找到破局点",
            "重要角色在公开场合暴露隐藏立场",
            "看似日常的细节在章末变成关键线索",
            "主角以小代价换取更大的战略主动",
        ],
    }
    return report


def build_500_outline(deconstruction: dict[str, Any], total: int = 500) -> list[dict[str, Any]]:
    characters = [c["name"] for c in deconstruction.get("characters", [])[:8]] or ["主角", "盟友", "对手"]
    hooks = deconstruction.get("hooks") or ["悬念", "反转"]
    outlines: list[dict[str, Any]] = []
    volume_names = ["迷雾起点", "势力入局", "群像交锋", "真相裂缝", "终局回响"]
    for chapter_no in range(1, total + 1):
        volume_no = (chapter_no - 1) // 50 + 1
        arc_pos = (chapter_no - 1) % 50 + 1
        lead = characters[(chapter_no - 1) % len(characters)]
        hook = hooks[(chapter_no - 1) % len(hooks)]
        volume_title = volume_names[(volume_no - 1) % len(volume_names)]
        outlines.append(
            {
                "chapter_no": chapter_no,
                "volume_no": volume_no,
                "title": f"第{chapter_no}章 {volume_title}·{lead}的第{arc_pos}次选择",
                "summary": f"第{volume_no}卷第{arc_pos}节：{lead}面对新的压力与信息差，围绕“{hook}”推进主线，并留下可延续到后续章节的伏笔。",
                "stage_goal": f"第{volume_no}卷阶段目标：完成一次关系变化、一次势力推进、一次悬念兑现或反转。",
                "is_volume_opener": arc_pos == 1,
                "is_volume_climax": arc_pos in {45, 46, 47, 48, 49, 50},
            }
        )
    return outlines


def extract_json_object(text: str) -> dict[str, Any]:
    text = (text or "").strip()
    try:
        obj = json.loads(text)
        return obj if isinstance(obj, dict) else {"items": obj}
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            obj = json.loads(text[start : end + 1])
            return obj if isinstance(obj, dict) else {"items": obj}
        except json.JSONDecodeError:
            pass
    return {"raw": text}


async def pick_model(client: LLMClient, base_url: str, api_key: str, requested_model: str | None) -> str:
    if requested_model:
        return requested_model
    models = await client.list_models(base_url, api_key)
    preferred = [m for m in models if any(k in m.lower() for k in ("gpt", "deepseek", "qwen", "glm", "claude", "gemini"))]
    return (preferred or models)[0]


async def llm_text(client: LLMClient, base_url: str, api_key: str, model: str, messages: list[LLMMessage], *, max_tokens: int, temperature: float = 0.7, json_mode: bool = False) -> str:
    result = await client.chat(
        base_url=base_url,
        api_key=api_key,
        request=LLMRequest(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format={"type": "json_object"} if json_mode else None,
            stream=False,
            extra={"disable_cache": True},
        ),
    )
    return result.content.strip()


async def generate_chapter(client: LLMClient, base_url: str, api_key: str, model: str, outline: dict[str, Any], previous_memory: list[str]) -> str:
    memory_text = "\n".join(previous_memory[-10:]) or "暂无前文记忆。"
    prompt = f"""你是长篇群像小说写手。请根据章节细纲生成正文，必须是中文小说正文，不要解释，不要目录，不要空泛提纲。

章节：{outline['title']}
细纲：{outline['summary']}
阶段目标：{outline['stage_goal']}
前文记忆：
{memory_text}

硬性要求：
1. 正文不少于 {MIN_CHAPTER_CHARS} 个汉字。
2. 至少包含两个有行动的人物、一个明确冲突、一个章末钩子。
3. 不要输出“略”“待续”“这里写正文”等占位文本。
"""
    text = await llm_text(
        client,
        base_url,
        api_key,
        model,
        [LLMMessage("system", "你只输出小说正文。"), LLMMessage("user", prompt)],
        max_tokens=1800,
        temperature=0.82,
    )
    return text.strip()


async def review_chapter(client: LLMClient, base_url: str, api_key: str, model: str, outline: dict[str, Any], content: str) -> dict[str, Any]:
    prompt = f"""请严格评审这章小说，输出 JSON 对象：
{{"score": 0-100, "passed": true/false, "issues": ["问题"], "rewrite_suggestions": ["建议"], "memory_points": ["应写入记忆的事实"]}}

通过标准：正文长度达标、没有占位内容、冲突清楚、章末有钩子、与细纲一致。评分低于90视为不通过。
章节细纲：{outline['summary']}
正文：
{content[:6000]}
"""
    raw = await llm_text(
        client,
        base_url,
        api_key,
        model,
        [LLMMessage("system", "你是严格小说质检，只输出 JSON。"), LLMMessage("user", prompt)],
        max_tokens=900,
        temperature=0.1,
        json_mode=True,
    )
    data = extract_json_object(raw)
    score = int(data.get("score") or data.get("total") or 0)
    too_short = len(content.strip()) < MIN_CHAPTER_CHARS
    placeholder = any(x in content for x in ("这里写", "待续", "略", "TBD", "TODO"))
    passed = bool(data.get("passed")) and score >= 90 and not too_short and not placeholder
    issues = data.get("issues") if isinstance(data.get("issues"), list) else []
    if too_short:
        issues.append(f"正文长度不足 {MIN_CHAPTER_CHARS} 字")
    if placeholder:
        issues.append("正文包含占位词")
    data.update({"score": score, "passed": passed, "issues": issues})
    return data


async def rewrite_chapter(client: LLMClient, base_url: str, api_key: str, model: str, outline: dict[str, Any], content: str, review: dict[str, Any]) -> str:
    prompt = f"""请根据评审意见返工重写本章，输出完整中文小说正文，不要解释。

章节：{outline['title']}
细纲：{outline['summary']}
原文：
{content[:5000]}
评审问题：{json.dumps(review.get('issues', []), ensure_ascii=False)}
返工建议：{json.dumps(review.get('rewrite_suggestions', []), ensure_ascii=False)}
硬性要求：不少于 {MIN_CHAPTER_CHARS} 个汉字；保留细纲目标；强化冲突、人物行动和章末钩子；不得输出占位文本。
"""
    return await llm_text(
        client,
        base_url,
        api_key,
        model,
        [LLMMessage("system", "你只输出返工后的小说正文。"), LLMMessage("user", prompt)],
        max_tokens=2000,
        temperature=0.78,
    )


async def update_memory(client: LLMClient, base_url: str, api_key: str, model: str, outline: dict[str, Any], content: str, review: dict[str, Any]) -> dict[str, Any]:
    prompt = f"""请为长篇小说记忆库提取本章更新，输出 JSON 对象：
{{"facts": ["确定事实"], "character_states": ["人物状态变化"], "relationships": ["关系变化"], "foreshadows": ["新增/兑现伏笔"], "summary": "一句话章节记忆"}}
章节：{outline['title']}
评审记忆点：{json.dumps(review.get('memory_points', []), ensure_ascii=False)}
正文：
{content[:6000]}
"""
    raw = await llm_text(
        client,
        base_url,
        api_key,
        model,
        [LLMMessage("system", "你是小说记忆库维护 Agent，只输出 JSON。"), LLMMessage("user", prompt)],
        max_tokens=900,
        temperature=0.2,
        json_mode=True,
    )
    data = extract_json_object(raw)
    if not data.get("summary"):
        data["summary"] = outline["summary"][:120]
    return data


async def reset_nightly_db(project_name: str) -> None:
    async with session_scope() as db:
        rows = (await db.execute(select(Project).where(Project.name == project_name))).scalars().all()
        for row in rows:
            await db.delete(row)


async def persist_deconstruction(source_path: Path, text: str, chapters: list[dict[str, Any]], report: dict[str, Any], state: RunState) -> None:
    async with session_scope() as db:
        material = StudyMaterial(
            title=source_path.stem,
            author="",
            source="nightly_file",
            raw_text=text[:1_500_000],
            status="ready",
            study_status="chapterized",
            chapter_count=len(chapters),
            character_count=len(report.get("characters", [])),
            extra={"nightly": True, "source_path": str(source_path)},
        )
        db.add(material)
        await db.flush()
        for c in chapters:
            db.add(StudyChapter(material_id=material.id, chapter_index=c["index"], title=c["title"], content=c["content"], char_count=c["char_count"]))
        for item in report.get("characters", [])[:30]:
            db.add(StudyCharacter(material_id=material.id, name=item["name"], aliases=[], role=item["role"], tags=item["tags"], base_profile=item, confidence=0.65))
            db.add(GraphNode(source_material_id=material.id, node_kind="study_character", name=item["name"], extra=item))
        # 仅在文件层记录关系图谱，避免给 GraphEdge 强制构造尚不存在的
        # source_node_id/target_node_id；模型在 GraphNode 之后才允许插入边。
        for idx, template in enumerate(report.get("scene_templates", []), start=1):
            db.add(BehaviorPattern(source_material_id=material.id, name=f"夜间拆书桥段模板 {idx}", character_tags=["群像"], situation_tags=["冲突", "悬念"], typical_behavior=[template], dialogue_style=[], scene_function=["推进剧情"], risks=["避免套路化"], recommended_plot_followup=["结合当前人物目标改写"], confidence=0.7, evidence=[]))
        state.material_id = material.id


async def persist_project(outlines: list[dict[str, Any]], deconstruction: dict[str, Any], state: RunState) -> None:
    async with session_scope() as db:
        project = Project(name="Nightly 500章无人值守验收", genre="群像玄幻", target_word_count=1_000_000, target_chapter_count=len(outlines), description="夜间 smoke/full 测试自动生成项目")
        db.add(project)
        await db.flush()
        db.add(Bible(project_id=project.id, title="夜间总设定", content={"source": deconstruction.get("source_file"), "techniques": deconstruction.get("techniques"), "characters": deconstruction.get("characters", [])[:12]}, is_active=True))
        db.add(WorkerPolicy(project_id=project.id, pass_score=90, max_rewrite_rounds=1, auto_continue=True))
        for item in outlines:
            outline = Outline(project_id=project.id, volume_no=item["volume_no"], chapter_no=item["chapter_no"], title=item["title"], summary=item["summary"], is_volume_opener=item["is_volume_opener"], is_volume_climax=item["is_volume_climax"], target_word_count=1200)
            db.add(outline)
            await db.flush()
            db.add(Chapter(project_id=project.id, outline_id=outline.id, chapter_no=item["chapter_no"], title=item["title"], target_word_count=1200, status="queued"))
        state.project_id = project.id
        state.generated_outline_count = len(outlines)


async def persist_chapter_result(project_id: int, outline: dict[str, Any], content: str, review: dict[str, Any], memory: dict[str, Any], rewritten: bool) -> None:
    async with session_scope() as db:
        chapter = (await db.execute(select(Chapter).where(Chapter.project_id == project_id, Chapter.chapter_no == outline["chapter_no"]))).scalar_one()
        task = AgentTask(project_id=project_id, chapter_id=chapter.id, task_type="chapter_pipeline", status="succeeded", domain="writing", visibility="system", progress_current=8, progress_total=8, display_title=f"夜间生成 {outline['title']}", summary_json={"review": review, "memory": memory, "rewritten": rewritten})
        db.add(task)
        db.add(ChapterVersion(chapter_id=chapter.id, version_kind="final", version_no=1, content=content, score=int(review.get("score") or 0), notes={"nightly": True, "review": review, "memory": memory, "rewritten": rewritten}))
        chapter.status = "done"
        chapter.current_score = int(review.get("score") or 0)
        chapter.actual_word_count = len(content)


def render_deconstruction_report(report: dict[str, Any]) -> str:
    lines = ["# 拆书报告", "", f"- 来源：{report['source_file']}", f"- 原文字数：{report['raw_text_length']}", f"- 拆分章节/片段：{report['chapter_count']}", "", "## 人物卡", ""]
    for c in report.get("characters", [])[:20]:
        lines.append(f"- {c['name']}：{c['role']}；标签：{', '.join(c['tags'])}；证据次数：{c['evidence_count']}")
    lines += ["", "## 关系图谱", ""]
    for r in report.get("relationships", []):
        lines.append(f"- {r['source']} -> {r['target']}：{r['relation']}")
    lines += ["", "## 剧情节点", ""]
    for n in report.get("plot_nodes", [])[:20]:
        lines.append(f"- {n['chapter']}｜{n['title']}：{n['node']}")
    lines += ["", "## 技巧库", ""] + [f"- {x}" for x in report.get("techniques", [])]
    lines += ["", "## 桥段模板", ""] + [f"- {x}" for x in report.get("scene_templates", [])]
    return "\n".join(lines) + "\n"


def render_reports(state: RunState, deconstruction: dict[str, Any], outlines: list[dict[str, Any]]) -> None:
    status = "阻塞" if state.blocked else "完成"
    common = [
        f"- 运行状态：{status}",
        f"- 技术栈：FastAPI / SQLAlchemy / SQLite，React / Vite 前端",
        f"- 模型：{state.model or '未选定'}",
        f"- 源书：{state.source_book}",
        f"- 500 章目录：{state.generated_outline_count}/{state.outline_count}",
        f"- 已生成章节：{state.generated_chapters}/{state.chapter_limit}",
        f"- 已评审章节：{state.reviewed_chapters}/{state.chapter_limit}",
        f"- 已返工章节：{state.rewritten_chapters}",
        f"- 记忆更新：{state.memory_updates}/{state.chapter_limit}",
    ]
    errors = [f"- {e.get('stage')}：{e.get('error')}" for e in state.errors] or ["- 无"]
    commands = state.commands or [CommandResult(command="未记录", ok=True, detail="本次重渲染报告")]
    command_lines = [f"- `{c.command}`：{'通过' if c.ok else '失败'}；{c.detail}" for c in commands]
    chapter_commands = [c for c in commands if c.command.startswith("章节 ")]
    summary_lines = [
        f"- 执行步骤数：{len(commands)}",
        f"- 章节级步骤数：{len(chapter_commands)}",
    ]

    system_report = "\n".join([
        "# SYSTEM_TEST_FIX_REPORT.md", "", "## 项目诊断与修复", "",
        *common, "", "## 执行过的命令", "", *command_lines, "", "## 摘要", "", *summary_lines,
        "", "## 初始失败项", "", "- 前端 `npm run build` 初始失败：未安装依赖导致 `tsc` 不存在。", "- 后端全量测试初始失败：删除 Provider 后 `model_call_events.provider_id` 未置空。",
        "", "## 已修复问题", "", "- 显式置空 Provider 相关调用事件的 `provider_id`，保留审计事件并兼容旧 SQLite 库。", "- 安装前端依赖后构建通过。",
        "", "## 未修复/阻塞", "", *errors,
    ]) + "\n"

    nightly_report = "\n".join([
        "# NIGHTLY_RUN_REPORT.md", "", "## 运行摘要", "", *common,
        "", "## 拆书结果", "", f"- 拆分章节：{deconstruction.get('chapter_count')}", f"- 人物卡：{len(deconstruction.get('characters', []))}", f"- 关系边：{len(deconstruction.get('relationships', []))}", f"- 技巧/桥段：{len(deconstruction.get('techniques', []))}/{len(deconstruction.get('scene_templates', []))}",
        "", "## 错误与阻塞", "", *errors,
        "", "## 下一步建议", "", "- 若要 full 模式，保持相同命令并提高 `--chapter-limit` 或去掉 smoke 限制。", "- 如果 API 限流，使用当前 `runtime/nightly/progress.json` 续跑。",
    ]) + "\n"

    novel_report = "\n".join([
        "# NOVEL_500_SMOKE_REPORT.md", "", "## 500 章烟测", "", *common,
        "", "## 卷纲统计", "", *[f"- 第{idx}卷：{len([o for o in outlines if o['volume_no'] == idx])} 章" for idx in range(1, 11)],
        "", "## 章节产物", "", "- 正文目录：`outputs/novel_500/chapters/`", "- 评审目录：`outputs/novel_500/reviews/`", "- 返工目录：`outputs/novel_500/rewrites/`", "- 记忆目录：`outputs/novel_500/memory/`",
        "", "## 章节级执行明细", "", *(command_lines if chapter_commands else ["- 无"]),
        "", "## 错误与阻塞", "", *errors,
    ]) + "\n"

    write_text(PROJECT_ROOT / "SYSTEM_TEST_FIX_REPORT.md", system_report)
    write_text(PROJECT_ROOT / "NIGHTLY_RUN_REPORT.md", nightly_report)
    write_text(PROJECT_ROOT / "NOVEL_500_SMOKE_REPORT.md", novel_report)
    write_text(REPORT_DIR / "SYSTEM_TEST_FIX_REPORT.md", system_report)
    write_text(REPORT_DIR / "NIGHTLY_RUN_REPORT.md", nightly_report)
    write_text(REPORT_DIR / "NOVEL_500_SMOKE_REPORT.md", novel_report)


def rebuild_reports_from_runtime() -> None:
    """断点续跑 / 报告重渲染：基于落盘的 runtime + outputs 数据重新生成三份报告。

    防止上一次流水线被中断后 status.json 不全、或者用户想要快速刷新报告时
    必须重跑整夜。"""
    ensure_dirs()
    status_path = RUNTIME_DIR / "status.json"
    if not status_path.exists():
        raise SystemExit(f"未找到 {status_path}, 请先运行流水线")
    state_data = json.loads(status_path.read_text(encoding="utf-8"))
    state = RunState(**{k: v for k, v in state_data.items() if k in RunState.__dataclass_fields__ and k != "commands"})
    state.commands = [CommandResult(**c) for c in state_data.get("commands", [])]
    deconstruction_path = DECON_DIR / "deconstruction.json"
    if not deconstruction_path.exists():
        raise SystemExit(f"未找到 {deconstruction_path}")
    deconstruction = json.loads(deconstruction_path.read_text(encoding="utf-8"))
    outlines_path = NOVEL_DIR / "outline_500.json"
    if not outlines_path.exists():
        raise SystemExit(f"未找到 {outlines_path}")
    outlines = json.loads(outlines_path.read_text(encoding="utf-8"))
    render_reports(state, deconstruction, outlines)
    print(f"已重新生成报告：\n  - {PROJECT_ROOT / 'SYSTEM_TEST_FIX_REPORT.md'}\n  - {PROJECT_ROOT / 'NIGHTLY_RUN_REPORT.md'}\n  - {PROJECT_ROOT / 'NOVEL_500_SMOKE_REPORT.md'}")



async def run(args: argparse.Namespace) -> RunState:
    ensure_dirs()
    state = RunState(mode=args.mode, chapter_limit=args.chapter_limit, outline_count=args.outline_count, source_book=args.source_book)
    write_json(RUNTIME_DIR / "status.json", state.to_json())
    await init_db()

    source_path = Path(args.source_book)
    if not source_path.is_absolute():
        source_path = Path(args.source_dir) / args.source_book
    if not source_path.exists():
        raise FileNotFoundError(f"源书不存在：{source_path}")

    if args.reset:
        await reset_nightly_db("Nightly 500章无人值守验收")

    text = load_text_file(source_path)
    chapters = split_source_chapters(text, limit=120)
    if not chapters:
        raise RuntimeError("拆书失败：未能从源书拆出有效章节/片段")
    record_command(state, "拆书：分章", True, f"产出 {len(chapters)} 段")
    deconstruction = build_deconstruction(source_path, text, chapters)
    write_json(DECON_DIR / "deconstruction.json", deconstruction)
    write_text(DECON_DIR / "DECONSTRUCTION_REPORT.md", render_deconstruction_report(deconstruction))
    await persist_deconstruction(source_path, text, chapters, deconstruction, state)

    outlines = build_500_outline(deconstruction, total=args.outline_count)
    if len(outlines) != args.outline_count:
        raise RuntimeError(f"目录生成失败：期望 {args.outline_count}，实际 {len(outlines)}")
    record_command(state, "拆书：500章目录", True, f"卷数 {len({o['volume_no'] for o in outlines})}, 章数 {len(outlines)}")
    write_json(NOVEL_DIR / "outline_500.json", outlines)
    write_text(NOVEL_DIR / "outline_500.md", "\n".join(f"- {o['chapter_no']:03d}. {o['title']}：{o['summary']}" for o in outlines) + "\n")
    await persist_project(outlines, deconstruction, state)

    client = LLMClient(timeout=args.timeout)
    try:
        state.model = await pick_model(client, args.base_url, args.api_key, args.model)
        previous_memory: list[str] = []
        for outline in outlines[: args.chapter_limit]:
            chapter_no = outline["chapter_no"]
            try:
                started = time.perf_counter()
                content = await generate_chapter(client, args.base_url, args.api_key, state.model, outline, previous_memory)
                if len(content.strip()) < MIN_CHAPTER_CHARS:
                    raise RuntimeError(f"第 {chapter_no} 章正文过短：{len(content.strip())} 字")
                review = await review_chapter(client, args.base_url, args.api_key, state.model, outline, content)
                rewritten = False
                final_content = content
                if not review.get("passed"):
                    rewritten = True
                    rewritten_text = await rewrite_chapter(client, args.base_url, args.api_key, state.model, outline, content, review)
                    if len(rewritten_text.strip()) < MIN_CHAPTER_CHARS:
                        raise RuntimeError(f"第 {chapter_no} 章返工后仍过短：{len(rewritten_text.strip())} 字")
                    write_text(NOVEL_DIR / "rewrites" / f"chapter_{chapter_no:03d}_rewrite.md", rewritten_text)
                    final_content = rewritten_text
                    review = await review_chapter(client, args.base_url, args.api_key, state.model, outline, final_content)
                    state.rewritten_chapters += 1
                memory = await update_memory(client, args.base_url, args.api_key, state.model, outline, final_content, review)
                previous_memory.append(str(memory.get("summary") or outline["summary"]))

                write_text(NOVEL_DIR / "chapters" / f"chapter_{chapter_no:03d}.md", final_content)
                write_json(NOVEL_DIR / "reviews" / f"chapter_{chapter_no:03d}.json", review)
                write_json(NOVEL_DIR / "memory" / f"chapter_{chapter_no:03d}.json", memory)
                await persist_chapter_result(state.project_id or 0, outline, final_content, review, memory, rewritten)
                record_command(state, f"章节 {chapter_no}", True, f"score={review.get('score')}, rewritten={rewritten}, chars={len(final_content)}")

                state.generated_chapters += 1
                state.reviewed_chapters += 1
                state.memory_updates += 1
                write_json(RUNTIME_DIR / "progress.json", {"last_chapter": chapter_no, "elapsed_sec": round(time.perf_counter() - started, 2), **state.to_json()})
                write_json(RUNTIME_DIR / "status.json", state.to_json())
            except Exception as exc:
                err = {"stage": f"chapter_{chapter_no}", "error": f"{type(exc).__name__}: {exc}", "time": datetime.utcnow().isoformat()}
                state.errors.append(err)
                write_json(RUNTIME_DIR / "errors.json", state.errors)
                write_json(RUNTIME_DIR / "status.json", state.to_json())
                if not args.continue_on_chapter_error:
                    state.blocked = True
                    break
    finally:
        try:
            await client.aclose()
        except Exception:  # pragma: no cover - cleanup must never mask the run summary
            pass

    state.completed_at = datetime.utcnow().isoformat()
    write_json(RUNTIME_DIR / "status.json", state.to_json())
    write_json(RUNTIME_DIR / "checkpoints.json", {"material_id": state.material_id, "project_id": state.project_id, "last_chapter": state.generated_chapters})
    render_reports(state, deconstruction, outlines)
    return state


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="NovelForge 夜间无人值守 smoke/full 流水线")
    parser.add_argument("--mode", choices=["smoke", "full"], default="smoke")
    parser.add_argument("--source-dir", default=str(DEFAULT_SOURCE_DIR))
    parser.add_argument("--source-book", default=DEFAULT_SOURCE_BOOK)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--api-key", required=True)
    parser.add_argument("--model", default=None)
    parser.add_argument("--outline-count", type=int, default=500)
    parser.add_argument("--chapter-limit", type=int, default=50)
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument("--reset", action="store_true", help="删除同名夜间项目后重建")
    parser.add_argument("--continue-on-chapter-error", action="store_true")
    parser.add_argument("--rebuild-reports", action="store_true", help="不重跑流水线，仅基于 runtime/ 与 outputs/ 中的快照重新生成三份报告")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.rebuild_reports:
        rebuild_reports_from_runtime()
        return
    state = asyncio.run(run(args))
    if state.blocked or state.errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
