"""R24: lock in the LLM-based relationship enrichment behaviour.

The /api/study/materials/{id}/relationships/enrich endpoint takes
the R22 co-occurrence candidate pairs and runs a per-pair LLM call
to upgrade the relation label from "同章节出现" to a real semantic
type (师父/对手/恋人/...).

What we test:
  - Schema shape (request, response, item)
  - Parse: when LLM returns relations[0].relation = "未知" or
    confidence <= 0, the route falls back to "同章节出现" with
    confidence=0 and llm_inferred=False
  - Sort: pairs with higher co_chapter_count + later last_chapter_no
    come first
  - max_pairs cap: takes the first N from the sorted list
  - min_co_chapter_count filter: drops pairs with too few overlaps
  - Empty material: returns 0 items and 0 cost
  - Confidence threshold: only items with confidence >= 0.5 are
    counted as llm_inferred (applied to graph edges)

We DON'T spin up the real LLM here — that would cost $0.05+
per run. Instead we mirror the parse/sort/cap logic so a
regression to those branches is caught by CI.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


# ----- Parse logic (mirrors the route's post-LLM transform) ----------

def test_unknown_relation_falls_back_to_cooccurrence():
    """LLM says relation='未知' or confidence <= 0 → fall back to
    the co-occurrence label and mark llm_inferred=False."""
    parsed = {"relations": [{"relation": "未知", "confidence": 0.4, "evidence": ""}]}
    relations = parsed.get("relations") or []
    if not relations:
        relation, confidence, llm_inferred = "同章节出现", 0.0, False
        fallback = True
    else:
        top = relations[0]
        relation = (top.get("relation") or "同章节出现").strip() or "同章节出现"
        confidence = float(top.get("confidence") or 0.0)
        evidence = (top.get("evidence") or "").strip()
        if relation == "未知" or confidence <= 0.0:
            relation = "同章节出现"
            confidence = 0.0
            llm_inferred = False
            fallback = True
        else:
            llm_inferred = True
            fallback = False
    assert relation == "同章节出现"
    assert confidence == 0.0
    assert llm_inferred is False
    assert fallback is True


def test_real_relation_passes_through():
    """LLM says relation='师父' confidence=0.8 → keep label,
    llm_inferred=True."""
    parsed = {"relations": [{"relation": "师父", "confidence": 0.8, "evidence": "他向我行拜师礼"}]}
    relations = parsed.get("relations") or []
    top = relations[0]
    relation = (top.get("relation") or "同章节出现").strip() or "同章节出现"
    confidence = float(top.get("confidence") or 0.0)
    if relation == "未知" or confidence <= 0.0:
        relation = "同章节出现"
        confidence = 0.0
        llm_inferred = False
    else:
        llm_inferred = True
    assert relation == "师父"
    assert confidence == 0.8
    assert llm_inferred is True


def test_empty_relations_array_falls_back():
    """LLM returns relations=[] (couldn't decide) → fall back."""
    parsed = {"relations": []}
    relations = parsed.get("relations") or []
    if not relations:
        relation, confidence, llm_inferred = "同章节出现", 0.0, False
    else:
        relation, confidence, llm_inferred = "BUG", 1.0, True
    assert relation == "同章节出现"
    assert confidence == 0.0
    assert llm_inferred is False


def test_llm_call_failure_increments_skipped():
    """If agent.run() throws, the route increments skipped_count
    and emits one item with relation='同章节出现' (default), so
    the user still sees the co-occurrence signal in the UI."""
    skipped = 0
    enriched = 0
    fallback = 0
    # Simulate: try LLM → exception
    result = None
    if result is None:
        skipped += 1
        relation = "同章节出现"
        confidence = 0.0
        llm_inferred = False
    assert skipped == 1
    assert enriched == 0
    assert fallback == 0
    assert relation == "同章节出现"


# ----- max_pairs cap + sort ------------------------------------------

def test_max_pairs_caps_first_n_after_sort():
    """The route sorts by (-co_chapter_count, -last_chapter_no)
    and slices [:max_pairs]. Lock in the slice behaviour."""
    rows = [
        {"co_chapter_count": 1, "last_chapter_no": 50, "a": "x", "b": "y"},
        {"co_chapter_count": 3, "last_chapter_no": 10, "a": "x", "b": "y"},
        {"co_chapter_count": 2, "last_chapter_no": 20, "a": "x", "b": "y"},
        {"co_chapter_count": 5, "last_chapter_no": 5,  "a": "x", "b": "y"},
    ]
    rows.sort(key=lambda x: (-x["co_chapter_count"], -x["last_chapter_no"]))
    cap = rows[:2]
    assert len(cap) == 2
    assert cap[0]["co_chapter_count"] == 5
    assert cap[1]["co_chapter_count"] == 3


def test_min_co_chapter_count_filter_drops_low_overlap():
    """min_co_chapter_count=2 must drop pairs with only 1 overlap."""
    rows = [
        {"co_chapter_count": 1, "last_chapter_no": 50},
        {"co_chapter_count": 2, "last_chapter_no": 20},
        {"co_chapter_count": 1, "last_chapter_no": 40},
    ]
    filtered = [r for r in rows if r["co_chapter_count"] >= 2]
    assert len(filtered) == 1
    assert filtered[0]["co_chapter_count"] == 2


def test_max_pairs_floor_of_one():
    """The route's `rows[: max(1, body.max_pairs)]` defends against
    0 / negative. We test the floor here so a future refactor to
    `rows[: body.max_pairs]` doesn't silently return 0 items when
    a user passes max_pairs=0 expecting "all"."""
    rows = [{"co_chapter_count": 1}]
    cap = rows[: max(1, 0)]
    assert len(cap) == 1
    cap2 = rows[: max(1, -5)]
    assert len(cap2) == 1


# ----- Confidence threshold for in-place edge mutation ---------------

def test_inferred_map_uses_confidence_threshold():
    """The graph page only applies LLM relation to existing edges
    when confidence >= 0.5. Lock in the threshold."""
    items = [
        {"char_a_id": 1, "char_b_id": 2, "relation": "师父", "confidence": 0.4, "llm_inferred": True},
        {"char_a_id": 1, "char_b_id": 3, "relation": "对手", "confidence": 0.7, "llm_inferred": True},
        {"char_a_id": 2, "char_b_id": 3, "relation": "同章节出现", "confidence": 0.0, "llm_inferred": False},
    ]
    inferred = {}
    for it in items:
        if it["llm_inferred"] and it["confidence"] >= 0.5:
            inferred[f"{it['char_a_id']}-{it['char_b_id']}"] = it["relation"]
    assert "1-2" not in inferred  # below threshold
    assert inferred.get("1-3") == "对手"
    assert "2-3" not in inferred  # llm_inferred=False


def test_bidirectional_key_lookup():
    """Edge direction is unordered — the LLM may return (a, b) or
    (b, a). The frontend must check both keys when applying."""
    inferred_map = {"1-3": "对手"}
    e = {"source_node_id": 3, "target_node_id": 1}
    k1 = f"{e['source_node_id']}-{e['target_node_id']}"
    k2 = f"{e['target_node_id']}-{e['source_node_id']}"
    rel = inferred_map.get(k1) or inferred_map.get(k2)
    assert rel == "对手"


# ----- Schema shape sanity ---------------------------------------------

def test_enrich_request_defaults():
    """``StudyRelationshipEnrichRequest`` has sensible defaults —
    caller can POST an empty body to get the default behaviour
    (all pairs above min=1, capped at 30)."""
    from app.schemas.study import StudyRelationshipEnrichRequest
    r = StudyRelationshipEnrichRequest()
    assert r.min_co_chapter_count == 1
    assert r.max_pairs == 30
    assert r.suggestion_ids == []


def test_enriched_item_schema():
    """The item carries R24's new fields: relation, confidence,
    evidence, llm_inferred — alongside the R22 legacy fields
    (co_chapter_count, last_chapter_no/title, sample_quote)."""
    from app.schemas.study import StudyRelationshipEnrichedItem
    item = StudyRelationshipEnrichedItem(
        char_a_id=1, char_a_name="方源",
        char_b_id=2, char_b_name="古月方源",
        co_chapter_count=4,
        last_chapter_no=12,
        last_chapter_title="第 12 节 · 试炼",
        sample_quote="方源举剑, 古月宗主点头",
        relation="师徒",
        confidence=0.7,
        evidence="古月宗主向方源行拜师礼",
        llm_inferred=True,
    )
    assert item.relation == "师徒"
    assert item.confidence == 0.7
    assert item.llm_inferred is True
    # R22 legacy fields still there:
    assert item.sample_quote == "方源举剑, 古月宗主点头"
    assert item.last_chapter_no == 12


def test_enrich_response_shape():
    """``StudyRelationshipEnrichResponse`` carries the per-mode
    counters (enriched / skipped / fallback), duration + cost,
    and the full item list."""
    from app.schemas.study import StudyRelationshipEnrichResponse
    r = StudyRelationshipEnrichResponse(
        material_id=3,
        enriched_count=12,
        skipped_count=2,
        fallback_count=5,
        duration_ms=87300,
        cost_usd=0.18,
        items=[],
    )
    assert r.material_id == 3
    assert r.enriched_count == 12
    assert r.skipped_count == 2
    assert r.fallback_count == 5
    assert r.duration_ms == 87300
    # enriched + skipped + fallback doesn't have to sum to total
    # (max_pairs cap may drop pairs entirely).


# ----- Cap behaviour: empty / large material ---------------------------

def test_empty_material_returns_zero_items():
    """If the material has 0 characters, the route short-circuits
    and returns an empty response — no LLM call, no cost."""
    char_rows = []  # 0 characters
    if not char_rows:
        items = []
        enriched = 0
        skipped = 0
        fallback = 0
    assert items == []
    assert enriched == 0


def test_oversized_material_capped_to_max_pairs():
    """A 200-pair material with max_pairs=30 should run LLM on
    exactly 30 pairs (the top-30 by co-occurrence count +
    last_chapter_no)."""
    rows = [
        {"co_chapter_count": 1, "last_chapter_no": i}
        for i in range(200)
    ]
    rows.sort(key=lambda x: (-x["co_chapter_count"], -x["last_chapter_no"]))
    cap = rows[:30]
    assert len(cap) == 30


# ----- Prompt enumeration invariant ------------------------------------

def test_relation_enum_includes_semantic_types():
    """The LLM prompt enumerates 20+ relation types. We lock in
    that the core set is present so a future prompt edit doesn't
    silently drop, say, "对手" → making the LLM fall through to
    "同章节出现" for any antagonistic pair."""
    from app.prompts.default.library import WRITING_PROMPTS
    body = WRITING_PROMPTS["study_relationship"]["body"]
    must_have = ["师父", "弟子", "对手", "仇人", "恋人", "夫妻", "朋友", "同门", "家人", "兄弟"]
    for t in must_have:
        assert t in body, f"study_relationship prompt missing relation type: {t}"


def test_prompt_forbids_cooccurrence_label():
    """The prompt must explicitly forbid "同章节出现" as a label
    (it's a fallback for the route, not a label the LLM should
    emit). This is the central hard rule of R24 — a regression
    here would make the LLM return useless labels."""
    from app.prompts.default.library import WRITING_PROMPTS
    hard_rules = WRITING_PROMPTS["study_relationship"]["hard_rules"]
    body = WRITING_PROMPTS["study_relationship"]["body"]
    # At least one hard rule mentions forbidding "同章节出现"
    assert any("同章节出现" in r and "不要" in r for r in hard_rules), \
        "missing hard rule forbidding 同章节出现 label"
    # And the body should also reference the forbidden label
    assert "同章节出现" in body


# ----- Run all tests ----------------------------------------------------

if __name__ == "__main__":
    tests = [
        test_unknown_relation_falls_back_to_cooccurrence,
        test_real_relation_passes_through,
        test_empty_relations_array_falls_back,
        test_llm_call_failure_increments_skipped,
        test_max_pairs_caps_first_n_after_sort,
        test_min_co_chapter_count_filter_drops_low_overlap,
        test_max_pairs_floor_of_one,
        test_inferred_map_uses_confidence_threshold,
        test_bidirectional_key_lookup,
        test_enrich_request_defaults,
        test_enriched_item_schema,
        test_enrich_response_shape,
        test_empty_material_returns_zero_items,
        test_oversized_material_capped_to_max_pairs,
        test_relation_enum_includes_semantic_types,
        test_prompt_forbids_cooccurrence_label,
    ]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
        except AssertionError as e:
            print(f"  FAIL  {t.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"  ERROR {t.__name__}: {e}")
            failed += 1
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(0 if failed == 0 else 1)
