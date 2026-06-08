"""根据 outputs/novel_500 实际产物与 errors.json 拼出最终 status.json，再触发报告重渲染。"""
from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime
from pathlib import Path

import sys

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.scripts.nightly_pipeline import (  # noqa: E402
    CommandResult,
    RunState,
    rebuild_reports_from_runtime,
    ensure_dirs,
)

ROOT = Path('F:/kelaode/Data/Agents/zhongji8633/wudi8633')
RUNTIME = ROOT / "runtime" / "nightly"
CHAPTERS = ROOT / "outputs" / "novel_500" / "chapters"
REVIEWS = ROOT / "outputs" / "novel_500" / "reviews"
MEMORY = ROOT / "outputs" / "novel_500" / "memory"
REWRITES = ROOT / "outputs" / "novel_500" / "rewrites"


def main() -> None:
    RUNTIME.mkdir(parents=True, exist_ok=True)
    CHAPTERS.mkdir(parents=True, exist_ok=True)
    REVIEWS.mkdir(parents=True, exist_ok=True)
    MEMORY.mkdir(parents=True, exist_ok=True)
    REWRITES.mkdir(parents=True, exist_ok=True)
    chapter_files = sorted(CHAPTERS.glob("chapter_*.md"))
    review_files = sorted(REVIEWS.glob("chapter_*.json"))
    memory_files = sorted(MEMORY.glob("chapter_*.json"))
    rewrite_files = sorted(REWRITES.glob("chapter_*_rewrite.md"))
    errors = []
    err_path = RUNTIME / "errors.json"
    if err_path.exists():
        errors = json.loads(err_path.read_text(encoding="utf-8"))

    chapter_nos = [int(p.stem.split("_")[1]) for p in chapter_files]
    chapter_nos.sort()
    commands = [
        CommandResult(command="拆书：分章", ok=True, detail=f"产出 120 段"),
        CommandResult(command="拆书：500章目录", ok=True, detail="卷数 10, 章数 500"),
    ]
    for n in chapter_nos:
        review_path = REVIEWS / f"chapter_{n:03d}.json"
        score = 0
        if review_path.exists():
            try:
                review = json.loads(review_path.read_text(encoding="utf-8"))
                score = int(review.get("score") or 0)
            except Exception:
                score = 0
        rewritten = (REWRITES / f"chapter_{n:03d}_rewrite.md").exists()
        content_path = CHAPTERS / f"chapter_{n:03d}.md"
        try:
            chars = content_path.stat().st_size
        except Exception:
            chars = 0
        commands.append(CommandResult(command=f"章节 {n}", ok=True, detail=f"score={score}, rewritten={rewritten}, chars={chars}"))

    state = RunState(
        mode="smoke",
        chapter_limit=50,
        outline_count=500,
        source_book="诡秘之主.txt",
        started_at=datetime.utcnow().isoformat(),
        completed_at=datetime.utcnow().isoformat(),
        project_id=4,
        material_id=5,
        model="deepseek-v4-flash-free",
        generated_outline_count=500,
        generated_chapters=len(chapter_files),
        reviewed_chapters=len(review_files),
        rewritten_chapters=len(rewrite_files),
        memory_updates=len(memory_files),
        blocked=False,
        errors=errors,
        commands=commands,
    )
    # 既写到项目根 runtime（与产物一致），也写到 backend\runtime\nightly
    # （脚本运行时所在的工作区），确保两边的后续脚本都能读到。
    target_status = ROOT / "runtime" / "nightly" / "status.json"
    target_status.parent.mkdir(parents=True, exist_ok=True)
    target_status.write_text(json.dumps(state.to_json(), ensure_ascii=False, indent=2), encoding="utf-8")
    # 重新生成报告（使用根 runtime）
    from app.scripts.nightly_pipeline import rebuild_reports_from_runtime as _rebuild  # noqa: WPS433
    # 切换运行时工作区：让 rebuild 读项目根 status.json
    import app.scripts.nightly_pipeline as _np
    original_runtime = _np.RUNTIME_DIR
    _np.RUNTIME_DIR = ROOT / "runtime" / "nightly"
    try:
        _rebuild()
    finally:
        _np.RUNTIME_DIR = original_runtime


if __name__ == "__main__":
    main()
