"""L2 test_06_chapter_pipeline_e2e.py — 章节流水线 E2E (mock LLM)。

目标: 不调用真实模型、不烧 token, 但走 `ChapterPipeline.run()` 的真实 DB 写入路径:
- Planner/Drafter/Critic/Continuity/MemoryUpdate/Learning 全部被 monkeypatch
- 产生 draft + final ChapterVersion
- 更新 Chapter.status/current_score/actual_word_count
- 返回总 cost/tokens/duration
"""
from __future__ import annotations

import pytest
from sqlalchemy import select


def fake_result(agent_name: str, *, raw: str, parsed: dict | None, cost_usd=0.0, input_tokens=1, output_tokens=1, duration_ms=1):
    from app.agents.base import AgentRunResult
    return AgentRunResult(
        step_id=1,
        agent_name=agent_name,
        parsed=parsed,
        raw=raw,
        resolved=None,
        duration_ms=duration_ms,
        cost_usd=cost_usd,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )


@pytest.mark.asyncio
async def test_chapter_pipeline_happy_path_mock_llm(client, db, monkeypatch):
    from app.agents.base import AgentRunResult
    from app.agents.planner import PlannerAgent
    from app.agents.drafter import DrafterAgent
    from app.agents.critic import CriticAgent
    from app.agents.continuity import ContinuityAgent
    from app.agents.memory_updater import MemoryUpdateAgent
    from app.agents.learner import LearningAgent
    from app.models.project import Project, Bible, Outline, Chapter, ChapterVersion
    from app.models.task import AgentTask, WorkerPolicy
    from app.workers.pipeline import ChapterPipeline

    project = Project(name="流水线测试书", genre="玄幻", target_word_count=100_000, target_chapter_count=100)
    db.add(project)
    await db.flush()
    db.add(Bible(project_id=project.id, title="主设定", content={"world": "灵气复苏"}, is_active=True))
    outline = Outline(project_id=project.id, chapter_no=1, title="第一章 山门", summary="入门")
    db.add(outline)
    await db.flush()
    chapter = Chapter(project_id=project.id, outline_id=outline.id, chapter_no=1, title="第一章 山门", target_word_count=1200)
    db.add(chapter)
    policy = WorkerPolicy(project_id=project.id, pass_score=80, max_rewrite_rounds=1)
    db.add(policy)
    await db.flush()
    task = AgentTask(
        project_id=project.id, chapter_id=chapter.id,
        task_type="write_chapter", status="running", domain="writing", visibility="user",
        progress_current=0, progress_total=8, payload={},
    )
    db.add(task)
    await db.commit()
    await db.refresh(project)
    await db.refresh(chapter)
    await db.refresh(task)

    async def planner_run(self, ctx):
        return fake_result(
            "PlannerAgent",
            raw='{"beats":["入山门","遇师长"],"goal":"建立主角目标"}',
            parsed={"beats": ["入山门", "遇师长"], "goal": "建立主角目标"},
            cost_usd=0.001, input_tokens=100, output_tokens=50, duration_ms=10,
        )

    async def drafter_run(self, ctx):
        text = "王陆站在山门前，风从云海里吹来。他抬头看见牌匾，心里忽然有了一个念头：既然来了，就要走到最高处。"
        return fake_result("DrafterAgent", raw=text, parsed={"content": text}, cost_usd=0.002, input_tokens=200, output_tokens=300, duration_ms=20)

    async def critic_run(self, ctx):
        return fake_result(
            "CriticAgent",
            raw='{"total":88,"issues":[],"strengths":["节奏清晰"]}',
            parsed={"total": 88, "issues": [], "strengths": ["节奏清晰"]},
            cost_usd=0.001, input_tokens=120, output_tokens=80, duration_ms=15,
        )

    async def noop_run(self, ctx):
        return fake_result("NoopAgent", raw="{}", parsed={}, cost_usd=0.0005, input_tokens=10, output_tokens=10, duration_ms=5)

    monkeypatch.setattr(PlannerAgent, "run", planner_run)
    monkeypatch.setattr(DrafterAgent, "run", drafter_run)
    monkeypatch.setattr(CriticAgent, "run", critic_run)
    monkeypatch.setattr(ContinuityAgent, "run", noop_run)
    monkeypatch.setattr(MemoryUpdateAgent, "run", noop_run)
    monkeypatch.setattr(LearningAgent, "run", noop_run)

    pipeline = ChapterPipeline(router=None, engine=None)
    result = await pipeline.run(db, task=task, chapter=chapter, policy=policy)
    await db.commit()

    assert result.chapter_id == chapter.id
    assert result.pass_status == "pass"
    assert result.final_score == 88
    assert result.rewrite_rounds == 0
    assert result.total_cost_usd == 0.0055
    assert result.total_input_tokens == 450
    assert result.total_output_tokens == 460

    refreshed = await db.get(Chapter, chapter.id)
    assert refreshed.status == "done"
    assert refreshed.current_score == 88
    assert refreshed.actual_word_count == len(result.final_text)

    rows = (await db.execute(
        select(ChapterVersion).where(ChapterVersion.chapter_id == chapter.id).order_by(ChapterVersion.id)
    )).scalars().all()
    kinds = [v.version_kind for v in rows]
    assert kinds == ["draft", "final"]
    assert rows[0].score == 88
    assert rows[1].score == 88
    assert "王陆站在山门前" in rows[1].content


@pytest.mark.asyncio
async def test_chapter_pipeline_rewrite_when_score_low(client, db, monkeypatch):
    """Critic 第一次低分 -> Rewriter -> Critic 第二次高分 -> final。"""
    from app.agents.base import AgentRunResult
    from app.agents.planner import PlannerAgent
    from app.agents.drafter import DrafterAgent
    from app.agents.critic import CriticAgent
    from app.agents.rewriter import RewriterAgent
    from app.agents.continuity import ContinuityAgent
    from app.agents.memory_updater import MemoryUpdateAgent
    from app.agents.learner import LearningAgent
    from app.models.project import Project, Bible, Chapter, ChapterVersion
    from app.models.task import AgentTask, WorkerPolicy
    from app.workers.pipeline import ChapterPipeline

    project = Project(name="改写测试书", genre="玄幻", target_word_count=100_000, target_chapter_count=100)
    db.add(project)
    await db.flush()
    db.add(Bible(project_id=project.id, title="主设定", content={}, is_active=True))
    chapter = Chapter(project_id=project.id, chapter_no=1, title="第一章", target_word_count=1200)
    db.add(chapter)
    policy = WorkerPolicy(project_id=project.id, pass_score=80, max_rewrite_rounds=1)
    db.add(policy)
    await db.flush()
    task = AgentTask(project_id=project.id, chapter_id=chapter.id, task_type="write_chapter", status="running", domain="writing", visibility="user", payload={})
    db.add(task)
    await db.commit()
    await db.refresh(chapter)
    await db.refresh(task)

    critic_calls = {"n": 0}

    async def planner_run(self, ctx):
        return fake_result("PlannerAgent", raw="{}", parsed={"beats": []}, cost_usd=0, input_tokens=1, output_tokens=1, duration_ms=1)

    async def drafter_run(self, ctx):
        return fake_result("DrafterAgent", raw="初稿", parsed={"content": "初稿"}, cost_usd=0, input_tokens=1, output_tokens=1, duration_ms=1)

    async def critic_run(self, ctx):
        critic_calls["n"] += 1
        score = 60 if critic_calls["n"] == 1 else 85
        return fake_result("CriticAgent", raw="{}", parsed={"total": score, "issues": [{"type": "节奏"}] if score < 80 else []}, cost_usd=0, input_tokens=1, output_tokens=1, duration_ms=1)

    async def rewriter_run(self, ctx):
        return fake_result("RewriterAgent", raw="改写稿", parsed={"rewritten_content": "改写稿", "changes": ["加强节奏"]}, cost_usd=0, input_tokens=1, output_tokens=1, duration_ms=1)

    async def noop_run(self, ctx):
        return fake_result("NoopAgent", raw="{}", parsed={}, cost_usd=0, input_tokens=1, output_tokens=1, duration_ms=1)

    monkeypatch.setattr(PlannerAgent, "run", planner_run)
    monkeypatch.setattr(DrafterAgent, "run", drafter_run)
    monkeypatch.setattr(CriticAgent, "run", critic_run)
    monkeypatch.setattr(RewriterAgent, "run", rewriter_run)
    monkeypatch.setattr(ContinuityAgent, "run", noop_run)
    monkeypatch.setattr(MemoryUpdateAgent, "run", noop_run)
    monkeypatch.setattr(LearningAgent, "run", noop_run)

    result = await ChapterPipeline(router=None, engine=None).run(db, task=task, chapter=chapter, policy=policy)
    await db.commit()

    assert result.rewrite_rounds == 1
    assert result.final_score == 85
    assert result.final_text == "改写稿"
    assert critic_calls["n"] == 2

    rows = (await db.execute(select(ChapterVersion).where(ChapterVersion.chapter_id == chapter.id).order_by(ChapterVersion.id))).scalars().all()
    assert [v.version_kind for v in rows] == ["draft", "rewrite_1", "final"]
    assert rows[-1].content == "改写稿"
