"""P9: DiscussionOrchestrator + ChiefDiscussionAgent

负责：根据 issue_type 选择 Agent、自动发言留痕、Chief 收敛结论、
      触发 RewriteTask / SkillBuilder。
      供 discussion_worker 轮询调用。
"""
from __future__ import annotations

import json
import time
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import AgentContext, BaseAgent
from app.core.database import AsyncSessionLocal
from app.models.discussion_trace import (
    DiscussionMessage,
    DiscussionSkillDraft,
    DiscussionThread,
)
from app.models.task import AgentTask
from app.services.llm.router import get_llm_router
from app.services.prompt_engine import get_prompt_engine
from app.services.discussion_trace import SkillBuilderService


# --- Agent 选择规则 ---
AGENT_RULES: dict[str, dict] = {
    "logic": {
        "required": ["critic", "planner", "drafter", "chief"],
        "optional": ["reader"],
    },
    "character": {
        "required": ["critic", "continuity", "drafter", "chief"],
        "optional": [],
    },
    "pacing": {
        "required": ["critic", "reader", "planner", "chief"],
        "optional": ["drafter"],
    },
    "continuity": {
        "required": ["continuity", "planner", "chief"],
        "optional": ["critic"],
    },
    "foreshadowing": {
        "required": ["continuity", "planner", "drafter", "chief"],
        "optional": ["memory"],
    },
    "style": {
        "required": ["critic", "drafter", "chief"],
        "optional": ["reader"],
    },
    "commercial_hook": {
        "required": ["reader", "critic", "planner", "chief"],
        "optional": ["drafter"],
    },
    "quality": {
        "required": ["critic", "planner", "chief"],
        "optional": ["drafter", "reader"],
    },
    "other": {
        "required": ["critic", "chief"],
        "optional": ["planner"],
    },
}

MAX_AGENT_MESSAGES = 6


class _DiscussionAgent(BaseAgent):
    """讨论 Agent — 使用 discussion_agent prompt 模板。"""
    name = "DiscussionAgent"
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


class _ChiefDiscussionAgent(BaseAgent):
    """Chief 讨论收敛 — 使用 discussion_chief_summary 模板。"""
    name = "ChiefDiscussionAgent"
    role = "Chief"
    prompt_key = "discussion_chief_summary"
    step_name = "discussion_chief_summary"
    uses_json_output = True
    allow_json_fallback = True
    extra_temperature = 0.3
    extra_max_tokens = 2000


class _SkillBuilderAgent(BaseAgent):
    """SkillBuilder — 从讨论提炼 Skill。"""
    name = "SkillBuilderAgent"
    role = "SkillBuilder"
    prompt_key = "discussion_skill_builder"
    step_name = "discussion_skill_builder"
    uses_json_output = True
    allow_json_fallback = True
    extra_temperature = 0.3
    extra_max_tokens = 1500


ROLE_TO_LLM: dict[str, str] = {
    "planner": "Planner",
    "drafter": "Drafter",
    "critic": "Critic",
    "continuity": "Continuity",
    "reader": "Reader",
    "memory": "Memory",
    "chief": "Chief",
    "skill_builder": "SkillBuilder",
}

ROLE_LABELS: dict[str, str] = {
    "planner": "策划", "drafter": "主笔", "critic": "审稿",
    "continuity": "连戏", "reader": "读者", "memory": "记忆官",
    "chief": "总编", "skill_builder": "SkillBuilder",
}


class DiscussionOrchestrator:
    """根据问题类型选择 Agent，自动发言留痕，Chief 收敛。"""

    async def run_thread(self, db: AsyncSession, thread_id: int) -> None:
        """执行一个讨论线程的完整流程。"""
        thread = await db.get(DiscussionThread, thread_id)
        if not thread:
            return

        thread.status = "discussing"
        thread.updated_at = datetime.utcnow()
        await db.flush()

        try:
            # 1. 选择 Agent
            agents = self.select_agents(thread.issue_type, thread.risk_level)

            # 2. 收集 issue sources 作为上下文
            from app.models.discussion_trace import DiscussionIssueSource
            sources = (await db.execute(
                select(DiscussionIssueSource)
                .where(DiscussionIssueSource.thread_id == thread_id)
                .order_by(DiscussionIssueSource.created_at.asc())
            )).scalars().all()

            evidence = "\n".join(
                f"[{s.source_type}] {s.problem_summary}" + (f'\n引用: "{s.quote}"' if s.quote else "")
                for s in sources
            )

            # 3. 逐个 Agent 发言
            router_ = get_llm_router()
            engine = get_prompt_engine()

            for agent_role in agents:
                if agent_role == "chief":
                    continue  # Chief 最后发言

                msg = await self._run_agent_message(
                    db=db,
                    thread=thread,
                    agent_role=agent_role,
                    evidence=evidence,
                    router_=router_,
                    engine=engine,
                )
                if msg:
                    # 更新 evidence 为后续 Agent 提供上下文
                    evidence += f"\n[{agent_role}] {msg.content[:200]}"

            # 4. Chief 汇总
            chief_msg = await self._run_chief_summary(
                db=db,
                thread=thread,
                router_=router_,
                engine=engine,
            )

            if chief_msg and chief_msg.parsed_output_json:
                parsed = chief_msg.parsed_output_json
                thread.final_decision = parsed.get("final_decision")
                thread.final_reason = parsed.get("reason")
                thread.final_action_json = parsed

                # 5. 创建 Rewrite 任务（如果 Chief 判断需要修改）
                rewrite_plan = parsed.get("rewrite_plan", {})
                if rewrite_plan.get("should_create_task") and thread.final_decision == "modify":
                    from app.models.task import AgentTask as Task
                    task = Task(
                        project_id=thread.project_id or 0,
                        chapter_id=thread.chapter_id,
                        task_type="rewrite_from_discussion",
                        status="pending",
                        instruction=rewrite_plan.get("instructions", ""),
                    )
                    db.add(task)
                    await db.flush()
                    thread.rewrite_task_id = task.id
                    thread.status = "rewrite_created"

                # 6. 创建 Skill 草案（如果 Chief 建议创建）
                skill_candidate = parsed.get("skill_candidate", {})
                if skill_candidate.get("should_create"):
                    try:
                        sb = SkillBuilderService()
                        draft = await sb.create_skill_draft_from_thread(
                            db=db,
                            thread_id=thread_id,
                            skill_data=skill_candidate,
                        )
                    except Exception:
                        pass  # Skill 草案创建失败不影响主流程

                # 更新状态
                if thread.status == "discussing":
                    thread.status = "converged"
            else:
                if thread.status == "discussing":
                    thread.status = "converged"

            thread.updated_at = datetime.utcnow()
            await db.commit()

        except Exception as exc:
            thread.status = "failed"
            thread.updated_at = datetime.utcnow()
            try:
                await db.commit()
            except Exception:
                pass

    def select_agents(self, issue_type: str, risk_level: str) -> list[str]:
        """根据问题类型和风险等级选择 Agent。"""
        rules = AGENT_RULES.get(issue_type, AGENT_RULES["other"])
        agents = list(rules["required"])

        # 高风险加可选 Agent
        if risk_level in ("high", "critical"):
            for opt in rules.get("optional", []):
                if opt not in agents:
                    agents.append(opt)

        # 确保 Chief 在最后
        if "chief" in agents:
            agents.remove("chief")
        agents.append("chief")

        # 限制最大数量
        return agents[:MAX_AGENT_MESSAGES]

    async def _run_agent_message(
        self,
        db: AsyncSession,
        thread: DiscussionThread,
        agent_role: str,
        evidence: str,
        router_,
        engine,
    ) -> DiscussionMessage | None:
        """跑一个 Agent 发言并保存。"""
        llm_role = ROLE_TO_LLM.get(agent_role, "Critic")
        agent = _DiscussionAgent(router_, engine, ROLE_LABELS.get(agent_role, agent_role), llm_role)

        try:
            async with AsyncSessionLocal() as isolated_db:
                task = AgentTask(
                    project_id=thread.project_id or 0,
                    task_type="discussion_turn",
                    status="running",
                    payload={"thread_id": thread.id, "role": agent_role},
                )
                isolated_db.add(task)
                await isolated_db.flush()

                ctx = AgentContext(
                    db=isolated_db, task=task,
                    project_id=thread.project_id or 0,
                    chapter_id=thread.chapter_id,
                    inputs={
                        "role_name": ROLE_LABELS.get(agent_role, agent_role),
                        "topic": thread.title,
                        "project_context": evidence[:2000],
                    },
                )
                t0 = time.time()
                result = await agent.run(ctx)
                elapsed = int((time.time() - t0) * 1000)

                task.status = "succeeded"
                task.finished_at = datetime.utcnow()
                await isolated_db.commit()

            parsed = result.parsed or {}
            content = parsed.get("perspective") or parsed.get("problem_judgement") or result.raw
            msg = DiscussionMessage(
                thread_id=thread.id,
                speaker_type="agent",
                speaker_role=agent_role,
                speaker_name=ROLE_LABELS.get(agent_role, agent_role),
                content=content[:5000],
                evidence_json=parsed.get("evidence"),
                decision_tags_json=parsed.get("decision_tags"),
                confidence=parsed.get("confidence"),
                provider_name=result.provider_name,
                model_name=result.model_name,
                raw_output=result.raw[:10000] if result.raw else None,
                parsed_output_json=parsed,
                token_in=result.input_tokens,
                token_out=result.output_tokens,
                cost_usd=result.cost_usd,
            )
            db.add(msg)
            await db.flush()
            return msg

        except Exception as exc:
            msg = DiscussionMessage(
                thread_id=thread.id,
                speaker_type="agent",
                speaker_role=agent_role,
                speaker_name=ROLE_LABELS.get(agent_role, agent_role),
                content="",
                error_message=str(exc)[:2000],
            )
            db.add(msg)
            await db.flush()
            return msg

    async def _run_chief_summary(
        self,
        db: AsyncSession,
        thread: DiscussionThread,
        router_,
        engine,
    ) -> DiscussionMessage | None:
        """Chief 汇总结论。"""
        # 收集之前的所有发言
        messages = (await db.execute(
            select(DiscussionMessage)
            .where(DiscussionMessage.thread_id == thread.id)
            .order_by(DiscussionMessage.created_at.asc())
        )).scalars().all()

        perspectives_json = json.dumps([
            {
                "role": m.speaker_role,
                "content": m.content[:500],
                "tags": m.decision_tags_json,
                "confidence": m.confidence,
            }
            for m in messages if not m.error_message
        ], ensure_ascii=False, indent=2)

        chief = _ChiefDiscussionAgent(router_, engine)

        try:
            async with AsyncSessionLocal() as isolated_db:
                task = AgentTask(
                    project_id=thread.project_id or 0,
                    task_type="discussion_chief_summary",
                    status="running",
                    payload={"thread_id": thread.id},
                )
                isolated_db.add(task)
                await isolated_db.flush()

                ctx = AgentContext(
                    db=isolated_db, task=task,
                    project_id=thread.project_id or 0,
                    chapter_id=thread.chapter_id,
                    inputs={
                        "topic": thread.title,
                        "perspectives_json": perspectives_json[:6000],
                    },
                )
                t0 = time.time()
                result = await chief.run(ctx)
                elapsed = int((time.time() - t0) * 1000)

                task.status = "succeeded"
                task.finished_at = datetime.utcnow()
                await isolated_db.commit()

            parsed = result.parsed or {}
            content = parsed.get("recommendation") or parsed.get("summary") or result.raw
            msg = DiscussionMessage(
                thread_id=thread.id,
                speaker_type="chief",
                speaker_role="chief",
                speaker_name="总编",
                content=content[:5000],
                decision_tags_json=parsed.get("accepted_points"),
                parsed_output_json=parsed,
                provider_name=result.provider_name,
                model_name=result.model_name,
                raw_output=result.raw[:10000] if result.raw else None,
                token_in=result.input_tokens,
                token_out=result.output_tokens,
                cost_usd=result.cost_usd,
            )
            db.add(msg)
            await db.flush()
            return msg

        except Exception as exc:
            msg = DiscussionMessage(
                thread_id=thread.id,
                speaker_type="chief",
                speaker_role="chief",
                speaker_name="总编",
                content="",
                error_message=str(exc)[:2000],
            )
            db.add(msg)
            await db.flush()
            return msg
