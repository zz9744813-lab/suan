"""R21: lock in the LLM router fallback fix.

Bug: when a role (e.g. ``StudyAgent``) had no explicit
``model_role_assignments`` row, ``LLMRouter.resolve`` used to
fall through to the lowest-id enabled provider — which on a
fresh DB is the built-in ``stub`` provider whose ``base_url`` is
``mock://local``. The ``_mock_chat`` path then returned the
canned ``_MOCK_STUDY`` envelope (book_title / world_rules /
character_archetypes / scene_kits / behavior_patterns), which
does NOT match the ``study_character`` prompt's expected
``{"characters":[...]}`` shape — every chapter got
``characters_added=0`` and the user stared at 2332 empty rows.

Fix: ``LLMRouter.resolve`` now refuses to pick a ``mock://``
provider for text agents. If the user has only mock providers
enabled, ``resolve`` raises a clean 400 instead of returning
placeholder content. Legacy bindings that point to mock/local
providers are skipped in favor of real API text providers.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import asyncio
from datetime import datetime
from unittest.mock import MagicMock

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.database import Base
from app.models.model_provider import ModelProvider, ModelRoleAssignment
from app.services.llm.router import LLMRouter


async def _setup_db():
    """Build a clean in-memory SQLite + return (sessionmaker, engine)."""
    eng = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = async_sessionmaker(eng, expire_on_commit=False)
    return sm, eng


async def _add_provider(sess, *, name: str, base_url: str, enabled: bool = True) -> ModelProvider:
    p = ModelProvider(
        name=name,
        base_url=base_url,
        api_key="dummy",
        default_model="some-model",
        enabled=enabled,
    )
    sess.add(p)
    await sess.flush()
    return p


async def _bind(sess, *, role: str, provider_id: int, model: str) -> ModelRoleAssignment:
    r = ModelRoleAssignment(
        role=role, provider_id=provider_id, model=model,
        temperature=0.0, max_tokens=2000, updated_at=datetime.utcnow(),
    )
    sess.add(r)
    await sess.flush()
    return r


# --- The actual scenarios ---------------------------------------------


def test_router_fallback_skips_mock_when_real_provider_exists():
    """If both stub (mock://) and a real provider are enabled, the
    fallback path MUST pick the real one — not the stub. This is
    the R21 regression guard.
    """
    async def run():
        sm, eng = await _setup_db()
        try:
            # Pass a MagicMock — ``resolve()`` never invokes the
            # client, so we sidestep the httpx-pool teardown that
            # would otherwise keep the event loop alive past the
            # ``asyncio.run`` return.
            router = LLMRouter(MagicMock())
            async with sm() as db:
                stub = await _add_provider(db, name="stub", base_url="mock://local")
                real = await _add_provider(db, name="whitedream", base_url="https://sub.whitedream.top/v1")
                # An unmapped role ("StudyAgent") with both providers enabled.
                resolved = await router.resolve(db, "StudyAgent")
                assert resolved.provider.id == real.id, (
                    f"fallback picked the mock stub (id={resolved.provider.id}) "
                    f"instead of the real provider (id={real.id})"
                )
                assert resolved.provider.base_url != stub.base_url
        finally:
            await eng.dispose()

    asyncio.run(run())


def test_router_fallback_picks_first_real_when_stub_disabled():
    """Defensive: even with the stub disabled, the fallback should
    pick the lowest-id real provider, not silently fall through.
    """
    async def run():
        sm, eng = await _setup_db()
        try:
            router = LLMRouter(MagicMock())
            async with sm() as db:
                await _add_provider(db, name="stub", base_url="mock://local", enabled=False)
                real = await _add_provider(db, name="whitedream", base_url="https://sub.whitedream.top/v1")
                resolved = await router.resolve(db, "StudyAgent")
                assert resolved.provider.id == real.id
        finally:
            await eng.dispose()

    asyncio.run(run())


def test_router_fallback_errors_when_only_mock_enabled():
    """If every enabled provider is a ``mock://`` stub, surface a
    clean 400 instead of returning canned placeholder content.
    The user has added no real provider yet, so the role has no
    way to make a real call — telling them "configure a real
    provider" beats silently 0-ing their bulk study.
    """
    async def run():
        sm, eng = await _setup_db()
        try:
            router = LLMRouter(MagicMock())
            async with sm() as db:
                await _add_provider(db, name="stub", base_url="mock://local")
                try:
                    await router.resolve(db, "StudyAgent")
                except HTTPException as exc:
                    assert exc.status_code == 400
                    assert "StudyAgent" in str(exc.detail) or "Provider" in str(exc.detail)
                else:
                    raise AssertionError("expected HTTPException when only mock providers enabled")
        finally:
            await eng.dispose()

    asyncio.run(run())


def test_router_explicit_mock_binding_skips_to_real_api():
    """An explicit legacy binding to ``mock://`` must not override
    the real API preference for text agents.
    """
    async def run():
        sm, eng = await _setup_db()
        try:
            router = LLMRouter(MagicMock())
            async with sm() as db:
                stub = await _add_provider(db, name="stub", base_url="mock://local")
                real = await _add_provider(db, name="whitedream", base_url="https://sub.whitedream.top/v1")
                # Explicitly bind "Draft" to the stub. The resolve() must
                # still prefer a real API text provider.
                await _bind(sess=db, role="Draft", provider_id=stub.id, model="stub-fast")
                resolved = await router.resolve(db, "Draft")
                assert resolved.provider.id == real.id
                assert resolved.provider.base_url != "mock://local"
        finally:
            await eng.dispose()

    asyncio.run(run())


def test_router_picks_lowest_id_real_provider():
    """When multiple real providers are enabled, the fallback
    picks the one with the lowest id (stable across calls).
    """
    async def run():
        sm, eng = await _setup_db()
        try:
            router = LLMRouter(MagicMock())
            async with sm() as db:
                # Stub at id=1, two real providers at id=2 and id=3.
                await _add_provider(db, name="stub", base_url="mock://local")
                real_a = await _add_provider(db, name="whitedream", base_url="https://sub.whitedream.top/v1")
                real_b = await _add_provider(db, name="other", base_url="https://api.example.com/v1")
                resolved = await router.resolve(db, "StudyAgent")
                # Lowest id among non-mock enabled providers wins.
                assert resolved.provider.id == real_a.id
        finally:
            await eng.dispose()

    asyncio.run(run())


if __name__ == "__main__":
    test_router_fallback_skips_mock_when_real_provider_exists()
    print("PASS: test_router_fallback_skips_mock_when_real_provider_exists")
    test_router_fallback_picks_first_real_when_stub_disabled()
    print("PASS: test_router_fallback_picks_first_real_when_stub_disabled")
    test_router_fallback_errors_when_only_mock_enabled()
    print("PASS: test_router_fallback_errors_when_only_mock_enabled")
    test_router_explicit_role_binding_still_uses_mock()
    print("PASS: test_router_explicit_role_binding_still_uses_mock")
    test_router_picks_lowest_id_real_provider()
    print("PASS: test_router_picks_lowest_id_real_provider")
    print("\nAll 5 router tests passed.")
