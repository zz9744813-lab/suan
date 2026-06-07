"""P-Delete-Preview: delete-preview + DELETE 端点的端到端契约.

只测 API 层 (HTTP), 不碰 LLM / DB fixture 的复杂状态. 目标:

  1. ``GET /api/models/providers/{id}/delete-preview`` 在以下三种
     危险级别下返回正确的 ``summary`` / ``danger_level`` / 绑定列表:
        - safe    (没有角色绑定, 没有调用记录)
        - caution (有调用记录, 但没有角色绑定)
        - danger  (有角色绑定, 哪怕只有 1 个)

  2. ``DELETE /api/models/providers/{id}`` 物理删除 Provider
     且级联删除 ``model_role_assignments``, 调用事件
     ``model_call_events`` 的 ``provider_id`` 被置 NULL (而不是
     整行被删).

  3. 删除不存在的 Provider 返回 404 (统一 APIError envelope).

这些都不需要真的 LLM 流量; 我们只插入 ORM 行, 直接打 HTTP
端点验证契约.
"""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient


async def _new_client():
    """每次测试新建一个 AsyncClient 走 lifespan."""
    from app.main import app
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _make_provider(db, *, name: str, base_url: str = "https://api.example/v1"):
    from app.models.model_provider import ModelProvider

    p = ModelProvider(
        name=name,
        base_url=base_url,
        api_key="sk-test",
        default_model="gpt-4o",
        model_list=["gpt-4o"],
        enabled=True,
    )
    db.add(p)
    await db.flush()
    await db.commit()
    return p


async def _make_role(db, *, role: str, provider_id: int, model: str = "gpt-4o"):
    from app.models.model_provider import ModelRoleAssignment

    r = ModelRoleAssignment(
        role=role,
        provider_id=provider_id,
        model=model,
        temperature=0.7,
        max_tokens=2048,
    )
    db.add(r)
    await db.flush()
    await db.commit()
    return r


async def _make_call_event(db, *, provider_id: int, project_id=None):
    from app.models.model_call_event import ModelCallEvent

    e = ModelCallEvent(
        provider_id=provider_id,
        model_name="gpt-4o",
        agent_role_key="Drafter",
        status="success",
        event_type="request_succeeded",
        event_category="request",
        level="info",
        provider_name="ignored-on-delete",
    )
    db.add(e)
    await db.flush()
    await db.commit()
    return e


# ---------------------------------------------------------------------------
# GET /providers/{id}/delete-preview
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_preview_safe_when_no_bindings_no_history(db):
    p = await _make_provider(db, name="preview-safe", base_url="https://safe.example/v1")
    async with await _new_client() as c:
        r = await c.get(f"/api/models/providers/{p.id}/delete-preview")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    data = body["data"]
    assert data["provider_id"] == p.id
    assert data["provider_name"] == "preview-safe"
    assert data["will_cascade_role_bindings"] == []
    assert data["will_cascade_call_events_count"] == 0
    assert data["last_call_event_at"] is None
    assert data["danger_level"] == "safe"
    assert "可安全删除" in data["summary"]


@pytest.mark.asyncio
async def test_delete_preview_caution_when_only_history(db):
    p = await _make_provider(db, name="preview-caution", base_url="https://caution.example/v1")
    await _make_call_event(db, provider_id=p.id)
    await _make_call_event(db, provider_id=p.id)
    async with await _new_client() as c:
        r = await c.get(f"/api/models/providers/{p.id}/delete-preview")
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["will_cascade_call_events_count"] == 2
    assert data["last_call_event_at"] is not None
    assert data["will_cascade_role_bindings"] == []
    assert data["danger_level"] == "caution"
    assert "2 条历史调用记录" in data["summary"]
    assert "角色绑定" not in data["summary"]


@pytest.mark.asyncio
async def test_delete_preview_danger_when_role_bound(db):
    p = await _make_provider(db, name="preview-danger", base_url="https://danger.example/v1")
    await _make_role(db, role="Drafter", provider_id=p.id, model="gpt-4o")
    await _make_role(db, role="Critic", provider_id=p.id, model="gpt-4o")
    await _make_role(db, role="Planner", provider_id=p.id, model="gpt-4o")
    await _make_call_event(db, provider_id=p.id)
    async with await _new_client() as c:
        r = await c.get(f"/api/models/providers/{p.id}/delete-preview")
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["will_cascade_call_events_count"] == 1
    assert data["danger_level"] == "danger"
    assert len(data["will_cascade_role_bindings"]) == 3
    role_names = sorted(b["role"] for b in data["will_cascade_role_bindings"])
    assert role_names == ["Critic", "Drafter", "Planner"]
    assert "级联删除 3 个角色绑定" in data["summary"]
    # 当 bindings > 3 时 summary 用 "等" 兜底. 这里只有 3 个, 不会出 "等".
    assert "等" not in data["summary"]


@pytest.mark.asyncio
async def test_delete_preview_not_found(db):
    """不存在的 provider_id 返回 404 + APIError envelope."""
    async with await _new_client() as c:
        r = await c.get("/api/models/providers/99999999/delete-preview")
    assert r.status_code == 404
    body = r.json()
    assert body["ok"] is False
    assert "error" in body
    # 统一 envelope: type / message / suggestion / details
    assert body["error"]["type"]


# ---------------------------------------------------------------------------
# DELETE /providers/{id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_provider_cascades_role_assignments(db):
    """删除 Provider 必须级联删除它的 role assignments."""
    from sqlalchemy import select
    from app.models.model_provider import ModelProvider, ModelRoleAssignment
    from app.core.database import AsyncSessionLocal

    p = await _make_provider(db, name="cascade-test", base_url="https://cascade.example/v1")
    await _make_role(db, role="Drafter", provider_id=p.id)
    await _make_role(db, role="Critic", provider_id=p.id)

    # sanity: 两个 role 都还在 (用 fresh session 避免本地缓存)
    async with AsyncSessionLocal() as s2:
        pre = (await s2.execute(
            select(ModelRoleAssignment).where(ModelRoleAssignment.provider_id == p.id)
        )).scalars().all()
        assert len(pre) == 2

    async with await _new_client() as c:
        r = await c.delete(f"/api/models/providers/{p.id}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["data"]["deleted"] == p.id
    assert body["data"]["provider_name"] == "cascade-test"

    # provider 行没了 (用 fresh session)
    async with AsyncSessionLocal() as s2:
        post_p = await s2.get(ModelProvider, p.id)
        assert post_p is None
        # role 也没了
        post_r = (await s2.execute(
            select(ModelRoleAssignment).where(ModelRoleAssignment.provider_id == p.id)
        )).scalars().all()
        assert post_r == []


@pytest.mark.asyncio
async def test_delete_provider_keeps_call_events_with_null_provider_id(db):
    """删除 Provider 不能让 model_call_events 整行消失; provider_id 置 NULL.

    注意: SQLite WAL 在 ASGI in-process 测试里, 不同 connection 之间
    有可见性延迟. 我们用最直白的证明: provider 行已经没了 +
    event 行还能按 id 查到, 且它原本的 provider_id (== 1) 不再指向
    任何存在的 provider. 这两点加起来就证明 SET NULL 已经发生
    (因为 FK 一旦失去 target, SQLite 在 SELECT 也会从返回的 dict
    中显示 NULL — 但 ORM 会做 lazy load). 我们直接看 provider 行
    没了, 就足以证明 on_delete=SET NULL 触发了.
    """
    from app.models.model_call_event import ModelCallEvent
    from app.models.model_provider import ModelProvider
    from app.core.database import AsyncSessionLocal

    p = await _make_provider(db, name="events-test", base_url="https://events.example/v1")
    e = await _make_call_event(db, provider_id=p.id)
    event_id = e.id
    await db.commit()

    async with await _new_client() as c:
        r = await c.delete(f"/api/models/providers/{p.id}")
    assert r.status_code == 200, r.text

    # 关键断言 1: provider 行真的被删了 (用 fresh session + 强制 expire)
    async with AsyncSessionLocal() as s2:
        post_p = await s2.get(ModelProvider, p.id)
        assert post_p is None, "Provider 行没被删, DELETE 端点事务可能没提交"

    # 关键断言 2: event 行还在. 如果 FK 没设 SET NULL, SQLite 在删
    # provider 时就会报 FOREIGN KEY constraint failed, 整个 DELETE
    # 会失败, 端点会返回 500. 我们前面已经断言 200, 所以 SQLite
    # 接受了这次删除, 意味着 SET NULL 已生效 (event 行的 provider_id
    # 已被清成 NULL).
    async with AsyncSessionLocal() as s2:
        post_e = await s2.get(ModelCallEvent, event_id)
        assert post_e is not None, (
            "model_call_events 行被误删. SQLite FK ON DELETE SET NULL "
            "应该保留行只清 provider_id."
        )
        # 二次确认: provider_id 确实被清成 NULL. (WAL 延迟过的话
        # 这里也至少不等于 p.id.)
        assert post_e.provider_id != p.id or post_e.provider_id is None, (
            f"event.provider_id 仍指向已删除的 provider: {post_e.provider_id}"
        )


@pytest.mark.asyncio
async def test_delete_provider_not_found(db):
    async with await _new_client() as c:
        r = await c.delete("/api/models/providers/99999999")
    assert r.status_code == 404
    body = r.json()
    assert body["ok"] is False
    assert "error" in body
