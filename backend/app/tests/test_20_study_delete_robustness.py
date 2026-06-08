"""拆书"删除此书"链路保护性测试 (用户报告: 拆书书架删除有异常).

回归覆盖:
- DELETE /api/study/materials/{id}?force=true 在材料有 study_chapters +
  study_characters + behavior_patterns + graph_nodes + graph_edges 的常
  见情况下必须 200, 不能 500.
- 不存在 material 必须 404 (业务错), 不是 500.
- 没传 force 时, 仍有 queued 状态的 run 必须 400 (业务错), 不是 500.
- 前端 StudyLibraryPage.handleDeleteBook 与 handleBatchDelete 都必须
  显式传 force=true (源码契约, 防回归).
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
import pytest_asyncio
import httpx

# 修正路径: app/tests/test_X.py -> parents[3] = wudi86333 项目根
FRONTEND = Path(__file__).resolve().parents[3] / "frontend" / "src" / "pages" / "StudyLibraryPage.tsx"


async def _create_material_with_core_orphans(client: httpx.AsyncClient) -> int:
    """创建一个含 study_chapters / study_characters / behavior_patterns
    / graph_nodes / graph_edges 的常见 material, 不依赖 deepstudy
    子表 (因为 deepstudy_* 表字段很多, 在测试里逐个填空容易
    因为 ORM 字段差异挂掉)."""
    from app.core.database import AsyncSessionLocal
    from app.models.study import (
        BehaviorPattern,
        GraphEdge,
        GraphNode,
        StudyChapter,
        StudyCharacter,
        StudyMaterial,
    )

    async with AsyncSessionLocal() as session:
        material = StudyMaterial(
            title="测试删除之书",
            author="P0-Test",
            source="paste",
            raw_text="第1章 起\n" + "角色与冲突在雨夜交织。\n" * 30,
            status="ready",
            study_status="chapterized",
            chapter_count=1,
            character_count=2,
        )
        session.add(material)
        await session.flush()

        session.add(StudyChapter(
            material_id=material.id, chapter_index=1, title="第1章 起",
            content="角色与冲突在雨夜交织。" * 30, char_count=600,
        ))
        for name in ("阿北", "雨夜"):
            session.add(StudyCharacter(
                material_id=material.id, name=name, aliases=[],
                role="主角", tags=["高频出场"], base_profile={"test": True},
                confidence=0.8,
            ))

        session.add(BehaviorPattern(
            source_material_id=material.id, name="夜雨对峙模板",
            character_tags=["阿北"], situation_tags=["雨夜"], typical_behavior=["对峙"],
            dialogue_style=[], scene_function=["推进"], risks=["套路化"],
            recommended_plot_followup=["升级冲突"], confidence=0.7, evidence=[],
        ))
        node_a = GraphNode(source_material_id=material.id, node_kind="study_character", name="阿北", extra={})
        node_b = GraphNode(source_material_id=material.id, node_kind="study_character", name="雨夜", extra={})
        session.add_all([node_a, node_b])
        await session.flush()
        session.add(GraphEdge(source_node_id=node_a.id, target_node_id=node_b.id, relation="co_occurs", weight=0.5, evidence=None))

        await session.commit()
        return material.id


async def _create_material_with_queued_run(client: httpx.AsyncClient) -> int:
    """创建一个含 queued run 的 material, 用于校验 force=false → 400."""
    from app.core.database import AsyncSessionLocal
    from app.models.deepstudy import StudyRun
    from app.models.study import StudyMaterial

    async with AsyncSessionLocal() as session:
        material = StudyMaterial(
            title="测试 force 校验之书",
            author="P0-Test",
            source="paste",
            raw_text="",
            status="draft",
            study_status="queued",
            chapter_count=0,
            character_count=0,
        )
        session.add(material)
        await session.flush()
        session.add(StudyRun(material_id=material.id, status="queued", mode="full",
                             total_chapters=0, processed_chapters=0))
        await session.commit()
        return material.id


@pytest.mark.asyncio
async def test_delete_material_with_core_orphans_returns_200(client: httpx.AsyncClient):
    """最常见场景: material + study_chapters + characters + behavior_patterns
    + graph_nodes + graph_edges. force=true 必须 200."""
    material_id = await _create_material_with_core_orphans(client)
    resp = await client.delete(
        f"/api/study/materials/{material_id}",
        params={"force": "true"},
    )
    assert resp.status_code == 200, (
        f"DELETE /api/study/materials/{material_id}?force=true 应当 200, "
        f"实际 {resp.status_code} body={resp.text[:300]}"
    )
    body = resp.json()
    assert body.get("ok") is True
    data = body.get("data") or {}
    deleted = data.get("deleted") or {}
    assert deleted.get("material") == 1
    assert deleted.get("chapters", 0) >= 1
    assert deleted.get("characters", 0) >= 1
    assert deleted.get("behavior_patterns", 0) >= 1
    assert deleted.get("graph_nodes", 0) >= 2
    assert deleted.get("graph_edges", 0) >= 1


@pytest.mark.asyncio
async def test_delete_material_not_found_returns_404(client: httpx.AsyncClient):
    """不存在的 material 必须 404, 不是 500."""
    resp = await client.delete("/api/study/materials/999999", params={"force": "true"})
    assert resp.status_code in (404, 400)
    assert resp.json().get("ok") is False


@pytest.mark.asyncio
async def test_delete_material_running_run_without_force_returns_400(client: httpx.AsyncClient):
    """不传 force 时, queued run 必须 400 (业务错误), 不能 500."""
    material_id = await _create_material_with_queued_run(client)
    try:
        resp = await client.delete(f"/api/study/materials/{material_id}")
        assert resp.status_code == 400, (
            f"DELETE 不带 force 期望 400, 实际 {resp.status_code} body={resp.text[:300]}"
        )
        body = resp.json()
        assert body.get("ok") is False
    finally:
        # 最后清理: 带 force 删
        await client.delete(
            f"/api/study/materials/{material_id}",
            params={"force": "true"},
        )


def test_frontend_handle_delete_uses_force_true():
    """前端 StudyLibraryPage.handleDeleteBook 必须传 force=true,
    防止有人改回 force=false 后用户点击直接 400."""
    src = FRONTEND.read_text(encoding="utf-8")
    # 在整个文件搜索 deleteStudyMaterialDeep 调用, 然后检查最后一个
    # 反括号前的 force 参数 (true|false), 跨多行, 允许 Array.from(...).
    for m in re.finditer(
        r"deleteStudyMaterialDeep\(([\s\S]*?)\)\s*;",
        src,
    ):
        args = m.group(1)
        if "true" in args or "false" in args:
            assert "true" in args and "false" not in args, (
                f"deleteStudyMaterialDeep 调用 force 参数应当 true, 实参: {args!r}"
            )
            return
    raise AssertionError("找不到 deleteStudyMaterialDeep 调用")


def test_frontend_bulk_delete_uses_force_true():
    """批量删除 handleBatchDelete 也必须传 force=true."""
    src = FRONTEND.read_text(encoding="utf-8")
    for m in re.finditer(
        r"batchDeleteStudyMaterials\(([\s\S]*?)\)\s*;",
        src,
    ):
        args = m.group(1)
        if "true" in args or "false" in args:
            assert "true" in args and "false" not in args, (
                f"batchDeleteStudyMaterials 调用 force 参数应当 true, 实参: {args!r}"
            )
            return
    raise AssertionError("找不到 batchDeleteStudyMaterials 调用")
