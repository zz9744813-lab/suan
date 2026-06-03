"""ChiefAgent (right-side chat panel) routes."""
from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.agents.base import AgentContext
from app.agents.chief import ChiefAgent, extract_json_block
from app.core.database import get_db
from app.core.errors import bad_request, not_found
from app.models.chief_agent import ChiefAgentMessage, ChiefAgentSession
from app.models.project import Chapter, Project
from app.models.task import AgentTask, WorkerStatus
from app.schemas import (
    APIResponse,
    ChiefAgentChatRequest,
    ChiefAgentMessageRead,
    ChiefAgentSessionRead,
)
from app.services.llm.router import get_llm_router
from app.services.prompt_engine import get_prompt_engine
from app.workers.worker import get_worker


router = APIRouter(prefix="/chief-agent", tags=["chief-agent"])


@router.get("/sessions", response_model=APIResponse[list[ChiefAgentSessionRead]])
async def list_sessions(
    project_id: int | None = None,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[list[ChiefAgentSessionRead]]:
    stmt = select(ChiefAgentSession).order_by(ChiefAgentSession.id.desc())
    if project_id is not None:
        stmt = stmt.where(ChiefAgentSession.project_id == project_id)
    rows = (await db.execute(stmt)).scalars().all()
    return {"ok": True, "data": [ChiefAgentSessionRead.model_validate(r) for r in rows]}


@router.post("/sessions", response_model=APIResponse[ChiefAgentSessionRead])
async def create_session(
    body: dict, db: AsyncSession = Depends(get_db)
) -> APIResponse[ChiefAgentSessionRead]:
    s = ChiefAgentSession(
        title=body.get("title", "新会话"),
        project_id=body.get("project_id"),
        page_context=body.get("page_context"),
    )
    db.add(s)
    await db.flush()
    return {"ok": True, "data": ChiefAgentSessionRead.model_validate(s)}


@router.get("/sessions/{session_id}/messages", response_model=APIResponse[list[ChiefAgentMessageRead]])
async def list_messages(
    session_id: int, db: AsyncSession = Depends(get_db)
) -> APIResponse[list[ChiefAgentMessageRead]]:
    rows = (await db.execute(
        select(ChiefAgentMessage)
        .where(ChiefAgentMessage.session_id == session_id)
        .order_by(ChiefAgentMessage.id.asc())
    )).scalars().all()
    return {"ok": True, "data": [ChiefAgentMessageRead.model_validate(r) for r in rows]}


@router.post("/chat", response_model=APIResponse[ChiefAgentMessageRead])
async def chat(
    body: ChiefAgentChatRequest, db: AsyncSession = Depends(get_db)
) -> APIResponse[ChiefAgentMessageRead]:
    # 1. session
    if body.session_id:
        session = await db.get(ChiefAgentSession, body.session_id)
        if session is None:
            raise not_found("ChiefAgentSession", body.session_id)
    else:
        session = ChiefAgentSession(
            title=body.message[:30] or "新会话",
            project_id=body.project_id,
            page_context=body.page_context,
        )
        db.add(session)
        await db.flush()
    if body.project_id and not session.project_id:
        session.project_id = body.project_id
    if body.page_context and not session.page_context:
        session.page_context = body.page_context

    # 2. user message
    user_msg = ChiefAgentMessage(
        session_id=session.id, role="user", content=body.message
    )
    db.add(user_msg)
    await db.flush()

    # 3. build context for the ChiefAgent
    project_state = "(no project)"
    if session.project_id:
        p = await db.get(Project, session.project_id)
        if p is not None:
            chap_count = (await db.execute(
                select(Chapter).where(Chapter.project_id == p.id)
            )).scalars().all()
            total_words = sum(c.actual_word_count for c in chap_count)
            project_state = (
                f"#{p.id} {p.name} | {p.genre} | "
                f"{len(chap_count)}/{p.target_chapter_count} chapters | "
                f"{total_words}/{p.target_word_count} words | status={p.status}"
            )
    worker_state = await get_worker().status()
    worker_summary = (
        f"state={worker_state['state']} | today_words={worker_state['today_words']} | "
        f"today_cost=${worker_state['today_cost_usd']:.3f} | "
        f"consecutive_failures={worker_state['consecutive_failures']}"
    )

    # 4. ensure there's a default task row tied to the message so the agent can
    #    persist steps. If we want a lightweight chat we can attach to a
    #    synthetic task. For MVP we attach to the user's session.
    synthetic_task = AgentTask(
        project_id=session.project_id or 0,
        task_type="chief_chat",
        status="running",
        payload={"session_id": session.id, "message_preview": body.message[:120]},
    )
    db.add(synthetic_task)
    await db.flush()

    # 5. invoke ChiefAgent
    inputs = {
        "user_message": body.message,
        "page_context": session.page_context or "chief-agent-panel",
        "project_state": project_state,
        "worker_state": worker_summary,
    }
    chief = ChiefAgent(get_llm_router(), get_prompt_engine())
    try:
        result = await chief.run(AgentContext(
            db=db, task=synthetic_task,
            project_id=session.project_id or 0,
            chapter_id=None, inputs=inputs,
        ))
    except Exception as exc:
        # fall back to a heuristic reply so the UI never goes silent
        fallback = {
            "reply": (
                f"收到消息「{body.message[:40]}」。当前 LLM 不可用（{exc}），"
                "请先在「模型配置」页配置一个可用的 Provider。"
            ),
            "actions": [
                {
                    "action_id": "open_models",
                    "type": "explain_models",
                    "label": "打开模型配置",
                    "description": "当前没有可用的模型，请先配置 Provider。",
                    "params": {},
                    "requires_confirm": False,
                }
            ],
            "thinking": "LLM 调用失败，提示用户配置模型。",
            "learning_notice": None,
        }
        msg = ChiefAgentMessage(
            session_id=session.id, role="chief",
            content=fallback["reply"],
            actions=fallback["actions"],
            thinking=fallback["thinking"],
        )
        db.add(msg)
        synthetic_task.status = "failed"
        synthetic_task.error = str(exc)
        await db.flush()
        return {"ok": True, "data": ChiefAgentMessageRead.model_validate(msg)}

    parsed = result.parsed or extract_json_block(result.raw) or {}
    reply_text = parsed.get("reply") or "(无回复)"
    actions = parsed.get("actions") or []
    thinking = parsed.get("thinking")

    msg = ChiefAgentMessage(
        session_id=session.id, role="chief",
        content=reply_text, actions=actions, thinking=thinking,
        tokens_in=result.input_tokens, tokens_out=result.output_tokens,
        cost_usd=result.cost_usd,
    )
    db.add(msg)
    synthetic_task.status = "succeeded"
    synthetic_task.finished_at = synthetic_task.finished_at  # touched
    synthetic_task.cost_usd = result.cost_usd
    synthetic_task.input_tokens = result.input_tokens
    synthetic_task.output_tokens = result.output_tokens
    await db.flush()
    return {"ok": True, "data": ChiefAgentMessageRead.model_validate(msg)}


@router.post("/actions/{action_id}/confirm")
async def confirm_action(
    action_id: str, body: dict, db: AsyncSession = Depends(get_db)
) -> APIResponse[dict]:
    """Execute a confirmed action. The body should include action_type and params."""
    action_type = body.get("action_type")
    params = body.get("params") or {}
    project_id = body.get("project_id")
    if action_type == "create_project":
        if not params.get("name"):
            raise bad_request("create_project 缺少 name")
        p = Project(
            name=params["name"],
            genre=params.get("genre", "玄幻"),
            target_word_count=int(params.get("target_word_count", 3_000_000)),
            target_chapter_count=int(params.get("target_chapter_count", 2000)),
            description=params.get("description"),
        )
        db.add(p)
        await db.flush()
        from app.models.project import Bible
        from app.models.task import WorkerPolicy
        db.add(Bible(project_id=p.id, title="主设定", content={}))
        db.add(WorkerPolicy(project_id=p.id))
        return {"ok": True, "data": {"action": "create_project", "project_id": p.id}}
    if action_type == "start_worker":
        await get_worker().start()
        return {"ok": True, "data": {"action": "start_worker"}}
    if action_type == "pause_worker":
        await get_worker().pause()
        return {"ok": True, "data": {"action": "pause_worker"}}
    if action_type == "create_chapter":
        from app.models.project import Chapter
        ch = Chapter(
            project_id=int(params["project_id"]),
            chapter_no=int(params.get("chapter_no", 1)),
            title=params.get("title", "未命名章节"),
            target_word_count=int(params.get("target_word_count", 3000)),
        )
        db.add(ch)
        await db.flush()
        # auto-enqueue
        task = AgentTask(
            project_id=ch.project_id, chapter_id=ch.id,
            task_type="chapter_pipeline", status="pending", priority=100,
        )
        db.add(task)
        await db.flush()
        return {"ok": True, "data": {"action": "create_chapter", "chapter_id": ch.id, "task_id": task.id}}
    raise bad_request(f"暂不支持的 action_type: {action_type}")
