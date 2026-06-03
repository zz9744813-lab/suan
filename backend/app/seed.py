"""Seed default prompt templates, model role defaults, and a singleton worker status row."""
from __future__ import annotations

import asyncio
from datetime import datetime

from sqlalchemy import select

from app.core.database import AsyncSessionLocal, init_db
from app.models.model_provider import ModelProvider, ModelRoleAssignment
from app.models.prompt import PromptTemplate, PromptVersion
from app.models.task import WorkerStatus
from app.prompts.default import WRITING_PROMPTS


DEFAULT_ROLE_ASSIGNMENTS: list[tuple[str, str, str, float, int]] = [
    # role, provider_name, model, temperature, max_tokens
    ("Chief", "stub", "stub-fast", 0.6, 1500),
    ("Planner", "stub", "stub-fast", 0.7, 1500),
    ("Draft", "stub", "stub-fast", 0.9, 4000),
    ("Critic", "stub", "stub-fast", 0.4, 1500),
    ("Rewrite", "stub", "stub-fast", 0.7, 4000),
    ("Continuity", "stub", "stub-fast", 0.3, 1200),
    ("MemoryUpdate", "stub", "stub-fast", 0.2, 1500),
    ("Learning", "stub", "stub-fast", 0.4, 1200),
    # R21: the Study (拆书) agents — StudyCharacterAgent /
    # StudyEventAgent / StudyBehaviorPatternAgent — all share the
    # ``role='StudyAgent'`` label, so one seed entry covers all
    # three. Without an explicit binding, ``LLMRouter.resolve``
    # falls back to the first enabled provider; if that provider
    # is the built-in stub (``mock://local``) the StudyCharacter
    # call would return the canned ``_MOCK_STUDY`` envelope
    # (book_title / world_rules / character_archetypes) which has
    # the WRONG JSON shape and silently 0's the user. The
    # router-level fix in ``app/services/llm/router.py`` now
    # refuses to fall through to ``mock://``, but seeding this row
    # keeps the no-network demo path consistent with the other
    # roles — the user can rebind to a real provider from the UI.
    ("StudyAgent", "stub", "stub-fast", 0.0, 2500),
]


async def seed() -> None:
    await init_db()
    async with AsyncSessionLocal() as db:
        # 1. Prompts
        for key, spec in WRITING_PROMPTS.items():
            tpl = (
                await db.execute(
                    select(PromptTemplate).where(PromptTemplate.template_key == key)
                )
            ).scalar_one_or_none()
            if tpl is None:
                tpl = PromptTemplate(
                    template_key=key,
                    name=spec["name"],
                    category=spec["category"],
                    role=spec["role"],
                    scope=spec["scope"],
                    genre=spec.get("genre"),
                    description=spec.get("description"),
                    allowed_inputs=spec.get("allowed_inputs", []),
                    forbidden_inputs=spec.get("forbidden_inputs", []),
                    output_schema=spec.get("output_schema"),
                    can_modify=spec.get("can_modify", []),
                    cannot_modify=spec.get("cannot_modify", []),
                    hard_rules=spec.get("hard_rules", []),
                )
                db.add(tpl)
                await db.flush()
            else:
                # R15 / Plan A: keep the template's metadata in sync with the
                # library spec on every seed run. Without this, allowed_inputs
                # and hard_rules on existing rows never update — the body
                # gets auto-bumped (see below) but the UI version viewer
                # keeps showing the old metadata. This 8-line sync makes the
                # whole template self-healing.
                tpl.name = spec["name"]
                tpl.category = spec["category"]
                tpl.role = spec["role"]
                tpl.scope = spec["scope"]
                tpl.genre = spec.get("genre")
                tpl.description = spec.get("description")
                tpl.allowed_inputs = spec.get("allowed_inputs", [])
                tpl.forbidden_inputs = spec.get("forbidden_inputs", [])
                tpl.output_schema = spec.get("output_schema")
                tpl.can_modify = spec.get("can_modify", [])
                tpl.cannot_modify = spec.get("cannot_modify", [])
                tpl.hard_rules = spec.get("hard_rules", [])
            # ensure v1 exists
            existing = (
                await db.execute(
                    select(PromptVersion).where(PromptVersion.template_id == tpl.id)
                )
            ).scalars().all()
            if not existing:
                ver = PromptVersion(
                    template_id=tpl.id, version=1, body=spec["body"],
                    status="active", change_note="initial seed",
                )
                db.add(ver)
                await db.flush()
                tpl.active_version_id = ver.id
            else:
                # Auto-bump: if the library body diverges from the active
                # version, snapshot a new version and switch the template
                # over. This lets code-side prompt tweaks propagate via
                # ``python -m app.seed`` without a manual "save new
                # version" dance. Existing v1 is preserved as deprecated
                # so the history page still shows the diff.
                active = next(
                    (v for v in existing if v.id == tpl.active_version_id),
                    next((v for v in existing if v.status == "active"), existing[0]),
                )
                if active and active.body != spec["body"]:
                    next_no = max(v.version for v in existing) + 1
                    # Demote current active to deprecated
                    active.status = "deprecated"
                    ver = PromptVersion(
                        template_id=tpl.id, version=next_no, body=spec["body"],
                        status="active",
                        change_note="auto-bump by seed: library body changed",
                    )
                    db.add(ver)
                    await db.flush()
                    tpl.active_version_id = ver.id

        # 2. A built-in stub provider so the system works out of the box.
        #    Uses the in-process mock LLM (`mock://`) so the UI and pipeline
        #    are runnable without any external API key. Users can later add a
        #    real provider and rebind roles in the "模型配置" page.
        stub = (
            await db.execute(
                select(ModelProvider).where(ModelProvider.name == "stub")
            )
        ).scalar_one_or_none()
        if stub is None:
            stub = ModelProvider(
                name="stub",
                base_url="mock://local",
                api_key="mock",
                default_model="mock-fast",
                model_list=["mock-fast", "mock-long", "mock-vision"],
                enabled=True,
                extra={"note": "Local mock LLM. Replace with a real OpenAI-compatible provider when ready."},
            )
            db.add(stub)
            await db.flush()
        else:
            # Upgrade old broken stub: switch to mock:// and enable it.
            if stub.base_url != "mock://local" or not stub.enabled:
                stub.base_url = "mock://local"
                stub.api_key = "mock"
                stub.default_model = stub.default_model or "mock-fast"
                stub.enabled = True
        # 3. Default role assignments
        for role, prov_name, model, temp, maxtok in DEFAULT_ROLE_ASSIGNMENTS:
            existing = (
                await db.execute(
                    select(ModelRoleAssignment).where(ModelRoleAssignment.role == role)
                )
            ).scalar_one_or_none()
            if existing is None:
                db.add(ModelRoleAssignment(
                    role=role, provider_id=stub.id, model=model,
                    temperature=temp, max_tokens=maxtok,
                    notes="default seed; please rebind to a real provider",
                ))

        # 4. WorkerStatus singleton
        ws = await db.get(WorkerStatus, 1)
        if ws is None:
            db.add(WorkerStatus(id=1, state="idle"))

        await db.commit()


if __name__ == "__main__":
    asyncio.run(seed())
    print("Seed complete.")
