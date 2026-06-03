"""Discussion Room — 多 Agent 圆桌讨论 (P0-FEAT-1)

每场讨论:
  1. 用户在 /discussion 页输入议题 + 勾选参与者
  2. 后端同时启动 N 个 Participant (角色对应到 LLM router 的 role)
  3. 全部结束后, 由 Synthesizer 一次性综合
  4. 整个 transcript 写回 DiscussionSession + DiscussionTurn
  5. 失败/部分失败也保存, 不让任何一次调用"白做"

为什么不用 chief_agent_sessions:
  - chief_agent 是 1:1 对话, role 字段只有 user/chief/system
  - DiscussionTurn 需要存 parsed (key_points, concerns) 结构化字段
  - Discussion 会有 N+1 条 turn, schema 不一样

并发说明:
  - asyncio.gather 不能共享同一个 AsyncSession 跑 flush
    (SQLite + async: "Session is already flushing")
  - 每个 participant 开自己的 AsyncSessionLocal, 跑完即关
  - 主 session 也有写事务, 会让 participant 的写失败 (database is locked)
  - 所以: 主 session 在 participant 之前先 commit, 然后 participant 跑完
    之后再用新 session 写 turn 行 + 汇总
"""
from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import AgentContext, BaseAgent
from app.core.database import AsyncSessionLocal, get_db
from app.core.errors import bad_request, not_found
from app.models.discussion import DiscussionSession, DiscussionTurn
from app.models.project import Project
from app.models.task import AgentTask
from app.schemas import APIResponse
from app.services.llm.router import get_llm_router
from app.services.prompt_engine import get_prompt_engine


router = APIRouter(prefix="/discussion", tags=["discussion"])


# 参与者在 UI 上的展示顺序 + 中文标签 + 背后调用的 LLM router role
PARTICIPANTS: dict[str, dict[str, str]] = {
    "planner":      {"label": "策划",   "role": "Planner"},
    "drafter":      {"label": "主笔",   "role": "Drafter"},
    "critic":       {"label": "审稿",   "role": "Critic"},
    "continuity":   {"label": "连戏",   "role": "Continuity"},
    "memory":       {"label": "记忆官", "role": "Memory"},
}


class RunRequest(BaseModel):
    project_id: int | None = None
    topic: str = Field(..., min_length=2, max_length=500)
    participants: list[str] = Field(
        ..., min_length=1, max_length=5,
        description="参与者 key 列表, 取自 PARTICIPANTS",
    )


class TurnOut(BaseModel):
    id: int
    turn_no: int
    agent_name: str
    role_label: str
    kind: str
    content: str
    parsed: dict[str, Any] | None = None
    error: str | None = None
    duration_ms: int
    cost_usd: float
    input_tokens: int
    output_tokens: int
    created_at: datetime


class SessionOut(BaseModel):
    id: int
    project_id: int | None
    topic: str
    participants: list[str]
    status: str
    error: str | None = None
    total_cost_usd: float
    total_input_tokens: int
    total_output_tokens: int
    created_at: datetime
    turns: list[TurnOut] = []


def _to_session_out(s: DiscussionSession, turns: list[DiscussionTurn]) -> SessionOut:
    return SessionOut(
        id=s.id, project_id=s.project_id, topic=s.topic,
        participants=s.participants or [], status=s.status, error=s.error,
        total_cost_usd=s.total_cost_usd,
        total_input_tokens=s.total_input_tokens,
        total_output_tokens=s.total_output_tokens,
        created_at=s.created_at,
        turns=[
            TurnOut(
                id=t.id, turn_no=t.turn_no, agent_name=t.agent_name,
                role_label=t.role_label, kind=t.kind, content=t.content,
                parsed=t.parsed, error=t.error,
                duration_ms=t.duration_ms, cost_usd=t.cost_usd,
                input_tokens=t.input_tokens, output_tokens=t.output_tokens,
                created_at=t.created_at,
            ) for t in turns
        ],
    )


class _Participant(BaseAgent):
    """Discussion Room 参与者 — 同一 prompt 模板, 不同 role_name。

    ``role`` (LLM router 用的) 由 ctor 注入, 决定走哪个模型的绑定。
    ``prompt_key`` 是讨论室专用模板 ``discussion_participant``。
    """
    name = "DiscussionParticipant"
    prompt_key = "discussion_participant"
    step_name = "discussion_turn"
    uses_json_output = True
    allow_json_fallback = True
    extra_temperature = 0.7
    extra_max_tokens = 1500

    def __init__(self, router, engine, role_name: str, llm_role: str):
        super().__init__(router, engine)
        self.role = llm_role
        self._role_name = role_name


class _Synthesizer(BaseAgent):
    """Chief 综合 — 用 discussion_synthesis 模板, 一次性产出结论。"""
    name = "ChiefAgent"
    role = "Chief"
    prompt_key = "discussion_synthesis"
    step_name = "discussion_synthesis"
    uses_json_output = True
    allow_json_fallback = True
    extra_temperature = 0.3
    extra_max_tokens = 2000


async def _run_participant_on_isolated_session(
    session_id: int,
    project_id: int,
    turn_idx: int,
    key: str,
    topic: str,
    project_context: str,
) -> dict:
    """一个 participant 跑一次, 用独立 session 避免 flush 冲突。

    Returns a kwargs dict ready to feed ``DiscussionTurn(**kwargs)``.
    """
    spec = PARTICIPANTS[key]
    router_ = get_llm_router()
    engine = get_prompt_engine()
    agent = _Participant(router_, engine, spec["label"], spec["role"])
    async with AsyncSessionLocal() as session:
        try:
            task = AgentTask(
                project_id=project_id,
                task_type="discussion_turn",
                status="running",
                payload={"session_id": session_id, "turn_idx": turn_idx, "role": spec["label"]},
            )
            session.add(task)
            await session.flush()
            ctx = AgentContext(
                db=session, task=task, project_id=project_id, chapter_id=None,
                inputs={
                    "role_name": spec["label"],
                    "topic": topic,
                    "project_context": project_context,
                },
            )
            t0 = time.time()
            result = await agent.run(ctx)
            elapsed = int((time.time() - t0) * 1000)
            task.status = "succeeded"
            task.finished_at = datetime.utcnow()
            parsed = result.parsed or {}
            content = parsed.get("perspective") or result.raw
            return {
                "agent_name": f"DiscussionParticipant[{spec['label']}]",
                "role_label": spec["label"],
                "kind": "participant",
                "content": content,
                "parsed": {
                    "key_points": parsed.get("key_points", []),
                    "concerns": parsed.get("concerns", []),
                },
                "error": None,
                "duration_ms": elapsed,
                "cost_usd": result.cost_usd,
                "input_tokens": result.input_tokens,
                "output_tokens": result.output_tokens,
            }
        except Exception as exc:
            elapsed = int((time.time() - t0) * 1000) if 't0' in locals() else 0
            try:
                task.status = "failed"
                task.error = str(exc)
                task.finished_at = datetime.utcnow()
                await session.commit()
            except Exception:
                pass
            return {
                "agent_name": f"DiscussionParticipant[{spec['label']}]",
                "role_label": spec["label"],
                "kind": "participant",
                "content": "",
                "parsed": None,
                "error": str(exc),
                "duration_ms": elapsed,
                "cost_usd": 0.0,
                "input_tokens": 0,
                "output_tokens": 0,
            }


@router.post("/run", response_model=APIResponse[SessionOut])
async def run_discussion(
    body: RunRequest, db: AsyncSession = Depends(get_db)
) -> APIResponse[SessionOut]:
    # 1. 校验 participants
    unknown = [p for p in body.participants if p not in PARTICIPANTS]
    if unknown:
        raise bad_request(f"未知的参与者: {unknown}; 可选: {list(PARTICIPANTS)}")

    # 2. 拉项目上下文 (如果有)
    project_context = "(无关联项目)"
    if body.project_id is not None:
        p = await db.get(Project, body.project_id)
        if p is None:
            raise not_found("Project", body.project_id)
        project_context = (
            f"#{p.id} {p.name} | 类型 {p.genre} | "
            f"目标 {p.target_word_count} 字 / {p.target_chapter_count} 章 | "
            f"状态 {p.status}"
        )

    # 3. 建 session (主 session 写)
    session = DiscussionSession(
        project_id=body.project_id, topic=body.topic,
        participants=body.participants, status="running",
    )
    db.add(session)
    await db.flush()
    session_id = session.id
    # 必须 commit, 否则 SQLite 会锁住整个 db, participant 写不进去
    await db.commit()

    # 4. 顺序跑所有参与者 — SQLite 不支持多 session 并发写
    #    (Postgres + 真实场景可以换 gather, 见上方 docstring)
    parallel_results = []
    for i, k in enumerate(body.participants):
        result = await _run_participant_on_isolated_session(
            session_id=session_id,
            project_id=body.project_id or 0,
            turn_idx=i,
            key=k,
            topic=body.topic,
            project_context=project_context,
        )
        parallel_results.append(result)

    # 5-8. 在新 session 里写 turn 行 + 跑综合 + 汇总
    #    (主 session 已经 commit 了, 不能复用; 用新 session 走到底)
    async with AsyncSessionLocal() as final_db:
        turn_rows: list[DiscussionTurn] = []
        for i, kw in enumerate(parallel_results, start=1):
            turn = DiscussionTurn(session_id=session_id, turn_no=i, **kw)
            final_db.add(turn)
            turn_rows.append(turn)
        await final_db.flush()

        ok_turns = [t for t in turn_rows if not t.error]
        failed_turns = [t for t in turn_rows if t.error]
        perspectives = [
            {
                "role": t.role_label,
                "perspective": (t.parsed or {}).get("perspective") or t.content,
                "key_points": (t.parsed or {}).get("key_points", []),
                "concerns": (t.parsed or {}).get("concerns", []),
            }
            for t in ok_turns
        ]
        perspectives_json = json.dumps(perspectives, ensure_ascii=False, indent=2)

        router_ = get_llm_router()
        engine = get_prompt_engine()
        try:
            synth_task = AgentTask(
                project_id=body.project_id or 0,
                task_type="discussion_synthesis",
                status="running",
                payload={"session_id": session_id, "ok_count": len(ok_turns), "failed_count": len(failed_turns)},
            )
            final_db.add(synth_task)
            await final_db.flush()
            synth = _Synthesizer(router_, engine)
            synth_ctx = AgentContext(
                db=final_db, task=synth_task,
                project_id=body.project_id or 0, chapter_id=None,
                inputs={"topic": body.topic, "perspectives_json": perspectives_json},
            )
            t0 = time.time()
            synth_result = await synth.run(synth_ctx)
            synth_elapsed = int((time.time() - t0) * 1000)
            synth_parsed = synth_result.parsed or {}
            synth_content = synth_parsed.get("recommendation") or synth_parsed.get("summary") or synth_result.raw
            synth_row_kwargs = {
                "agent_name": "ChiefAgent", "role_label": "总编",
                "kind": "synthesis",
                "content": synth_content,
                "parsed": {
                    "summary": synth_parsed.get("summary", ""),
                    "agreement": synth_parsed.get("agreement", []),
                    "tension": synth_parsed.get("tension", []),
                    "recommendation": synth_parsed.get("recommendation", ""),
                    "next_actions": synth_parsed.get("next_actions", []),
                },
                "error": None,
                "duration_ms": synth_elapsed,
                "cost_usd": synth_result.cost_usd,
                "input_tokens": synth_result.input_tokens,
                "output_tokens": synth_result.output_tokens,
            }
            synth_task.status = "succeeded"
            synth_task.finished_at = datetime.utcnow()
        except Exception as exc:
            synth_elapsed = int((time.time() - t0) * 1000) if 't0' in locals() else 0
            synth_row_kwargs = {
                "agent_name": "ChiefAgent", "role_label": "总编",
                "kind": "synthesis",
                "content": "", "parsed": None, "error": str(exc),
                "duration_ms": synth_elapsed,
                "cost_usd": 0.0, "input_tokens": 0, "output_tokens": 0,
            }
            try:
                synth_task.status = "failed"
                synth_task.error = str(exc)
                synth_task.finished_at = datetime.utcnow()
            except Exception:
                pass

        synth_row = DiscussionTurn(
            session_id=session_id, turn_no=len(turn_rows) + 1, **synth_row_kwargs
        )
        final_db.add(synth_row)
        turn_rows.append(synth_row)
        await final_db.flush()

        total_in = sum(t.input_tokens for t in turn_rows)
        total_out = sum(t.output_tokens for t in turn_rows)
        total_cost = sum(t.cost_usd for t in turn_rows)
        if failed_turns and not ok_turns and synth_row.error:
            new_status = "failed"
            new_error = "全部参与者失败, 综合也失败"
        elif failed_turns or synth_row.error:
            new_status = "partial"
            new_error = (
                f"{len(failed_turns)} 位参与者失败: " + ", ".join(t.role_label for t in failed_turns)
                if failed_turns else "综合步骤失败"
            )
        else:
            new_status = "succeeded"
            new_error = None
        # 直接 UPDATE 避免和 SELECT 抢锁
        from sqlalchemy import update
        await final_db.execute(
            update(DiscussionSession)
            .where(DiscussionSession.id == session_id)
            .values(
                status=new_status, error=new_error,
                total_input_tokens=total_in, total_output_tokens=total_out,
                total_cost_usd=total_cost,
            )
        )
        await final_db.commit()

    # 主 session 也同步状态(用于 response, 不会再被 commit)
    session.status = new_status
    session.error = new_error
    session.total_input_tokens = total_in
    session.total_output_tokens = total_out
    session.total_cost_usd = total_cost

    return {"ok": True, "data": _to_session_out(session, turn_rows)}


@router.get("/sessions", response_model=APIResponse[list[SessionOut]])
async def list_sessions(
    project_id: int | None = None,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[list[SessionOut]]:
    stmt = select(DiscussionSession).order_by(DiscussionSession.id.desc()).limit(limit)
    if project_id is not None:
        stmt = stmt.where(DiscussionSession.project_id == project_id)
    sessions = (await db.execute(stmt)).scalars().all()
    out: list[SessionOut] = []
    for s in sessions:
        turns = (await db.execute(
            select(DiscussionTurn)
            .where(DiscussionTurn.session_id == s.id)
            .order_by(DiscussionTurn.turn_no.asc())
        )).scalars().all()
        out.append(_to_session_out(s, turns))
    return {"ok": True, "data": out}


@router.get("/sessions/{session_id}", response_model=APIResponse[SessionOut])
async def get_session(
    session_id: int, db: AsyncSession = Depends(get_db),
) -> APIResponse[SessionOut]:
    s = await db.get(DiscussionSession, session_id)
    if s is None:
        raise not_found("DiscussionSession", session_id)
    turns = (await db.execute(
        select(DiscussionTurn)
        .where(DiscussionTurn.session_id == s.id)
        .order_by(DiscussionTurn.turn_no.asc())
    )).scalars().all()
    return {"ok": True, "data": _to_session_out(s, turns)}
