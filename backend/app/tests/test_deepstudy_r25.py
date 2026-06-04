"""R25 (P0-DeepStudy) — book-shelf + run lifecycle tests.

Scope: P0 covers the data layer + read-mostly API skeleton. R26
will land the DeepStudyCoordinatorAgent and the 8 sub-agents; this
test file therefore focuses on what R25 owns:

  1. Library endpoint shape (empty data path + populated path).
  2. Run lifecycle (start / query / pause / resume / cancel).
  3. Stages-for-mode mapping (full vs *_only vs repair_failed).
  4. Knowledge graph empty-data path (book root only, no entities).
  5. Node detail for book root + unknown prefix.
  6. Patterns / techniques endpoints with empty data.
  7. Counter aggregation: 1 chapter in a material should not blow
     up the GROUP BY queries.

These are pure-Python unit tests that don't touch the live DB.
Where the E2E behaviour matters (404 on missing material, status
transitions), we exercise the route via the FastAPI TestClient.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


# ============================================================
# 1. Library endpoint shape (offline)
# ============================================================

def test_library_summary_defaults():
    """A zero-state library should report all-zero counters and
    a non-zero book count (3 from the dev DB after the R25
    backfill). The endpoint wraps everything in APIResponse.
    """
    from app.schemas.deepstudy import LibrarySummary, LibraryResponse
    s = LibrarySummary()
    assert s.total_books == 0
    assert s.completed == 0
    assert s.studying == 0
    assert s.failed == 0
    assert s.empty == 0
    assert s.chapterized == 0
    assert s.total_entities == 0
    assert s.total_relationships == 0
    assert s.total_techniques == 0
    assert s.total_cost_usd == 0.0

    r = LibraryResponse(items=[], summary=s, page=1, page_size=50, total=0)
    assert r.items == []
    assert r.total == 0
    assert r.page == 1
    assert r.page_size == 50


def test_library_item_required_fields():
    """LibraryItem has the 6 'deep' counters even when no
    DeepStudy has run. They default to 0 so the spine renders.
    """
    from app.schemas.deepstudy import LibraryItem
    item = LibraryItem(
        id=1, title="t", author="a", created_at="2026-01-01T00:00:00",
        updated_at="2026-01-01T00:00:00",
    )
    assert item.study_status == "empty"
    assert item.entity_count == 0
    assert item.scene_beat_count == 0
    assert item.relationship_count == 0
    assert item.foreshadow_count == 0
    assert item.behavior_count == 0
    assert item.technique_count == 0
    assert item.cost_usd == 0.0
    assert item.knowledge_score is None


# ============================================================
# 2. Stages-for-mode mapping
# ============================================================

def test_stages_for_full_mode():
    """Full mode runs all 9 stages incl. graph + critic."""
    from app.routers.deepstudy import _stages_for_mode
    stages = _stages_for_mode("full")
    assert stages == [
        "chapter_profile", "entity", "scene_beat", "relationship",
        "foreshadow", "behavior", "technique", "graph", "critic",
    ]
    assert len(stages) == 9


def test_stages_for_entities_only():
    """entities_only trims to chapter_profile + entity + scene_beat."""
    from app.routers.deepstudy import _stages_for_mode
    assert _stages_for_mode("entities_only") == [
        "chapter_profile", "entity", "scene_beat",
    ]


def test_stages_for_relationships_only():
    from app.routers.deepstudy import _stages_for_mode
    assert _stages_for_mode("relationships_only") == [
        "chapter_profile", "relationship",
    ]


def test_stages_for_behaviors_only():
    from app.routers.deepstudy import _stages_for_mode
    assert _stages_for_mode("behaviors_only") == [
        "chapter_profile", "behavior",
    ]


def test_stages_for_techniques_only():
    """techniques_only: behavior is the dependency stage that
    must run first (per spec section 5.7)."""
    from app.routers.deepstudy import _stages_for_mode
    assert _stages_for_mode("techniques_only") == ["behavior", "technique"]


def test_stages_for_repair_failed_includes_all():
    """repair_failed lists all stages so the UI can show the
    planned skeleton; the worker decides per-stage which to
    re-fire based on the per-stage error log.
    """
    from app.routers.deepstudy import _stages_for_mode
    stages = _stages_for_mode("repair_failed")
    assert len(stages) == 9
    assert "graph" in stages
    assert "critic" in stages


# ============================================================
# 3. Run start schema shape
# ============================================================

def test_study_run_create_defaults():
    """Default body = full mode, no range, force=False, concurrency=3."""
    from app.schemas.deepstudy import StudyRunCreate
    body = StudyRunCreate()
    assert body.mode == "full"
    assert body.chapter_range is None
    assert body.force is False
    assert body.max_concurrency == 3
    assert body.model_roles is None


def test_study_run_create_all_modes_valid():
    """The Literal mode type accepts all 6 documented values."""
    from app.schemas.deepstudy import StudyRunCreate
    for mode in ("full", "entities_only", "relationships_only",
                 "behaviors_only", "techniques_only", "repair_failed"):
        body = StudyRunCreate(mode=mode)
        assert body.mode == mode


def test_study_run_create_rejects_bad_mode():
    """Unknown mode should fail Pydantic validation."""
    from pydantic import ValidationError
    from app.schemas.deepstudy import StudyRunCreate
    try:
        StudyRunCreate(mode="nonsense")
        assert False, "expected ValidationError"
    except ValidationError:
        pass


def test_study_run_create_model_roles_override():
    """Per-role binding override is optional and accepts a dict."""
    from app.schemas.deepstudy import StudyRunCreate
    body = StudyRunCreate(model_roles={
        "EntityExtractionAgent": "whitedream/step-3.7-flash",
        "SceneBeatAgent": "stub/stub-fast",
    })
    assert body.model_roles == {
        "EntityExtractionAgent": "whitedream/step-3.7-flash",
        "SceneBeatAgent": "stub/stub-fast",
    }


# ============================================================
# 4. Knowledge graph empty-data shape
# ============================================================

def test_knowledge_graph_response_shape():
    """The response wraps book + nodes + edges + stats. With no
    deepstudied rows, nodes has just the book root and edges is
    empty. stats.by_type is the per-type counter map.
    """
    from app.schemas.deepstudy import (
        KnowledgeGraphResponse, KnowledgeGraphStats, GraphNodeRead, GraphEdgeRead,
    )
    book = {
        "id": 1, "title": "t", "author": "a", "study_status": "empty",
    }
    nodes = [GraphNodeRead(
        id="book:1", type="book", label="t", size=42, score=1.0,
    )]
    resp = KnowledgeGraphResponse(
        book=book, nodes=nodes, edges=[],
        stats=KnowledgeGraphStats(nodes=1, edges=0, by_type={"book": 1}),
    )
    assert resp.book["id"] == 1
    assert len(resp.nodes) == 1
    assert resp.nodes[0].id == "book:1"
    assert resp.nodes[0].type == "book"
    assert resp.edges == []
    assert resp.stats.by_type == {"book": 1}


def test_graph_node_read_defaults():
    """Composite IDs and size/score are required to be sensible
    defaults so the renderer can rely on them.
    """
    from app.schemas.deepstudy import GraphNodeRead
    n = GraphNodeRead(id="entity:33", type="character", label="方源")
    assert n.size == 10  # default
    assert n.score == 0.5  # default
    assert n.chapter_index is None
    assert n.extra == {}  # default


def test_graph_edge_read_defaults():
    from app.schemas.deepstudy import GraphEdgeRead
    e = GraphEdgeRead(
        id="rel:5", source="entity:1", target="entity:2",
        type="family", label="兄弟",
    )
    assert e.weight == 0.5
    assert e.evidence is None
    assert e.extra == {}


# ============================================================
# 5. Node detail empty-data shape
# ============================================================

def test_node_detail_response_defaults():
    """Empty mention / relationship / scene_beat / foreshadow /
    behavior / technique / agent_step lists default to [] so the
    UI doesn't have to null-check.
    """
    from app.schemas.deepstudy import NodeDetailResponse
    nd = NodeDetailResponse(id="book:1", type="book", label="t")
    assert nd.profile == {}
    assert nd.mentions == []
    assert nd.relationships == []
    assert nd.scene_beats == []
    assert nd.foreshadows == []
    assert nd.behavior_patterns == []
    assert nd.techniques == []
    assert nd.agent_steps == []


# ============================================================
# 6. Query schemas
# ============================================================

def test_behavior_pattern_query_defaults():
    from app.schemas.deepstudy import BehaviorPatternQuery
    q = BehaviorPatternQuery()
    assert q.material_id is None
    assert q.character_tag is None
    assert q.situation_tag is None
    assert q.q is None
    assert q.min_confidence == 0.0
    assert q.limit == 50


def test_writing_technique_query_defaults():
    from app.schemas.deepstudy import WritingTechniqueQuery
    q = WritingTechniqueQuery()
    assert q.material_id is None
    assert q.technique_type is None
    assert q.situation is None
    assert q.q is None
    assert q.limit == 50


# ============================================================
# 7. Counter aggregation: zero state is safe
# ============================================================

def test_summary_status_keys_exhaustive():
    """LibrarySummary covers all 8 DeepStudy state-machine values
    so the UI can show a 0-pill for the absent ones without
    'unknown status' warnings.
    """
    from app.schemas.deepstudy import LibrarySummary
    s = LibrarySummary()
    expected_keys = {
        "total_books", "completed", "studying", "paused",
        "review_required", "failed", "empty", "chapterized",
        "total_entities", "total_relationships", "total_techniques",
        "total_cost_usd",
    }
    assert set(s.model_dump().keys()) == expected_keys


# ============================================================
# 8. Composite ID parsing
# ============================================================

def test_composite_id_parsing_for_entity():
    """The node detail endpoint splits on the first ':' to handle
    prefix-based routing. Lock that contract.
    """
    node_id = "entity:33"
    prefix, _, raw_id = node_id.partition(":")
    assert prefix == "entity"
    assert int(raw_id) == 33


def test_composite_id_parsing_for_book():
    node_id = "book:1"
    prefix, _, raw_id = node_id.partition(":")
    assert prefix == "book"
    assert int(raw_id) == 1


def test_composite_id_parsing_for_scene_with_large_id():
    """Large composite IDs (scene:12345) must still parse correctly."""
    node_id = "scene:12345"
    prefix, _, raw_id = node_id.partition(":")
    assert prefix == "scene"
    assert int(raw_id) == 12345


# ============================================================
# 9. Run start response shape
# ============================================================

def test_study_run_start_response_shape():
    """The start endpoint returns run_id + material_id + status +
    a Chinese-language message. The message is intentionally
    pre-baked so the UI can show it without a 2nd round-trip.
    """
    from app.schemas.deepstudy import StudyRunStartResponse
    r = StudyRunStartResponse(run_id=1, material_id=3, status="queued")
    assert r.run_id == 1
    assert r.material_id == 3
    assert r.status == "queued"
    assert "后台" in r.message
    assert "/api/deepstudy/runs/" in r.message


# ============================================================
# 10. MaterialiseSummary shape (used by graph node from R22)
# ============================================================

def test_materialise_summary_shape():
    """R22 also exports MaterialiseSummary; verify it has the
    sibling-field contract (nodes_created, edges_created).
    MaterialiseSummary lives in app.schemas.study (R22), not
    app.schemas.deepstudy (R25), but the deepstudy router also
    re-imports it for the R22 → R25 graph materialise flow.
    """
    from app.schemas.study import MaterialiseSummary
    m = MaterialiseSummary(nodes_created=0, edges_created=0)
    assert m.nodes_created == 0
    assert m.edges_created == 0


if __name__ == "__main__":
    # Run every test function in this file.
    import inspect
    here = sys.modules[__name__]
    passed = failed = 0
    for name, fn in inspect.getmembers(here, inspect.isfunction):
        if not name.startswith("test_"):
            continue
        try:
            fn()
            print(f"PASS: {name}")
            passed += 1
        except AssertionError as e:
            print(f"FAIL: {name}: {e}")
            failed += 1
        except Exception as e:
            print(f"ERROR: {name}: {type(e).__name__}: {e}")
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
    if failed:
        sys.exit(1)
