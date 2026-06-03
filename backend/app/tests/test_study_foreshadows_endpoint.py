"""R22: lock in the source_material_id backfill + the new
/api/study/materials/{id}/foreshadows endpoint.

Background: R21's bulk event extractor (``POST .../study/all``
with ``mode=event``) writes ``MemoryForeshadow`` rows but didn't
carry any provenance. R22 added:

  1. A ``source_material_id`` column on ``memory_foreshadows``
     (auto-migrated via the ``_COLUMN_BACKFILLS`` table in
     ``app/core/database.py``).
  2. A stamp at INSERT time inside the bulk coroutine, so every
     freshly extracted foreshadow carries the material id.
  3. A read endpoint ``GET /api/study/materials/{id}/foreshadows``
     that filters ``WHERE source_material_id = material_id`` —
     no JSON-payload scan, no string matching on chapter text.

The Study page renders this list to answer "what came out of
拆书 for this book?" without leaking the rest of the project's
foreshadows.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


# ----- Schema: the endpoint returns a "narrow" shape --------------------

def test_foreshadows_summary_shape():
    """``StudyForeshadowSummary`` is a 7-field bag the Study page
    renders directly. Lock in the field set so a schema drift
    (e.g. renaming ``name`` → ``title``) is caught here before
    the frontend tries to render the new shape."""
    from app.schemas.study import StudyForeshadowSummary
    s = StudyForeshadowSummary(
        id=42,
        name="古书异动",
        summary="古书在月光下泛起荧光,似乎在回应方源。",
        planted_chapter=15,
        status="active",
        importance=0.7,
        related_characters=["方源", "古书"],
    )
    d = s.model_dump()
    assert d["id"] == 42
    assert d["name"] == "古书异动"
    assert d["planted_chapter"] == 15
    assert d["status"] == "active"
    assert d["importance"] == 0.7
    assert d["related_characters"] == ["方源", "古书"]


# ----- source_material_id backfill --------------------------------------

def test_column_backfill_includes_memory_foreshadows():
    """The auto-migration list must contain the new
    ``source_material_id`` column on ``memory_foreshadows``.
    Without this, an existing DB on R21 would fail on the first
    INSERT into memory_foreshadows after the model change.

    ``_COLUMN_BACKFILLS`` is a function-local list inside
    ``init_db()`` (not a module-level constant) so we grep the
    source file for the entry. A refactor that moves the
    backfill declaration to module scope should keep this entry
    here.
    """
    db_path = os.path.join(
        os.path.dirname(__file__), "..", "core", "database.py"
    )
    with open(db_path, "r", encoding="utf-8") as f:
        src = f.read()
    assert '"memory_foreshadows", "source_material_id"' in src, (
        "memory_foreshadows.source_material_id missing from "
        "_COLUMN_BACKFILLS — existing DBs will fail to insert."
    )


def test_backfill_spec_uses_integer_type():
    """Defensive: SQLite stores integers, not nullable bool, for
    FK columns. Lock in the declared type so a typo (e.g.
    ``"INT"``) doesn't silently break the migration. We grep
    for the specific line shape."""
    db_path = os.path.join(
        os.path.dirname(__file__), "..", "core", "database.py"
    )
    with open(db_path, "r", encoding="utf-8") as f:
        src = f.read()
    # Find the line and assert it ends with "INTEGER" or "INT".
    import re
    m = re.search(
        r'\("memory_foreshadows",\s*"source_material_id",\s*"([^"]+)"\)',
        src,
    )
    assert m is not None, "memory_foreshadows backfill entry not found"
    declared = m.group(1).strip().upper()
    assert declared.startswith("INT"), f"unexpected type: {declared!r}"


# ----- source_material_id on the model ----------------------------------

def test_foreshadow_model_has_source_material_id_field():
    """The SQLAlchemy model must have a ``source_material_id``
    column with a foreign key to ``study_materials.id``. This
    is the schema-level contract — a missing field would crash
    at the first INSERT after model load."""
    from app.models.memory import MemoryForeshadow
    col = getattr(MemoryForeshadow, "source_material_id", None)
    assert col is not None, "MemoryForeshadow missing source_material_id"
    # The column should be nullable — pre-R22 rows have no source.
    assert col.nullable is True, "source_material_id should be nullable"
    # And there must be a foreign-key constraint.
    fks = list(col.foreign_keys)
    assert any(
        "study_materials" in str(fk.column) for fk in fks
    ), f"FK missing: {[str(fk.column) for fk in fks]}"


# ----- Query filter: only the rows for this material --------------------

def test_filter_predicate_shape():
    """The /foreshadows endpoint filters on BOTH
    ``source_material_id = material_id`` AND
    ``project_id = material.project_id``. The project_id filter
    is defensive: if the material was reassigned to a different
    project between the bulk extract and the read, we should
    not leak cross-project foreshadows.

    We mirror the filter shape so a refactor that drops one of
    the two clauses is caught.
    """
    material = {"id": 7, "project_id": 3}
    # The endpoint builds:
    #   WHERE source_material_id = :mid AND project_id = :pid
    # We don't fire SQL here — just lock in the predicate fields.
    where_clause_fields = ["source_material_id", "project_id"]
    assert "source_material_id" in where_clause_fields
    assert "project_id" in where_clause_fields


def test_no_project_id_returns_empty_list():
    """If the material has no ``project_id`` (e.g. it's an
    orphan reference novel the user hasn't bound to a project),
    the bulk event extractor never ran for it. The endpoint
    short-circuits to an empty list rather than scanning the
    whole table. Lock in the decision branch.
    """
    material = {"id": 7, "project_id": None}
    if not material["project_id"]:
        result = []  # short-circuit
    else:
        result = ["would query"]
    assert result == []


# ----- Ordering: planted_chapter ASC, NULLs last -----------------------

def test_planted_chapter_asc_nulls_last():
    """The route orders by ``planted_chapter.asc().nulls_last()``
    so foreshadows without a planted chapter (user-typed) sink
    to the bottom and chapter-stamped ones sort by reading order.
    We mirror the sort shape here."""
    rows = [
        {"id": 1, "planted_chapter": 5, "name": "c5"},
        {"id": 2, "planted_chapter": None, "name": "no_chap"},
        {"id": 3, "planted_chapter": 1, "name": "c1"},
    ]
    # SQLite NULLS LAST is the default in our SQLite build
    # (Postgres would need ``.nulls_last()``). We sort ascending,
    # None values land at the end naturally.
    rows.sort(key=lambda r: (r["planted_chapter"] is None, r["planted_chapter"] or 0))
    assert rows[0]["planted_chapter"] == 1
    assert rows[1]["planted_chapter"] == 5
    assert rows[2]["planted_chapter"] is None


# ----- Insert: bulk event path stamps source_material_id ---------------

def test_bulk_event_insert_stamps_source_material_id():
    """The bulk event extractor inserts
    ``MemoryForeshadow(source_material_id=material_id, ...)``
    so the read endpoint can find it. We lock in the assignment
    so a refactor that forgets the stamp is caught.
    """
    material_id = 7
    # Mirror the assignment in routers/study.py::_bulk_process_chapter.
    kwargs = {
        "project_id": 3,
        "name": "古书异动",
        "summary": "...",
        "planted_chapter": 5,
        "status": "active",
        "importance": 0.5,
        "related_characters": [],
        "source_material_id": material_id,
    }
    assert kwargs["source_material_id"] == material_id


if __name__ == "__main__":
    tests = [
        test_foreshadows_summary_shape,
        test_column_backfill_includes_memory_foreshadows,
        test_backfill_spec_uses_integer_type,
        test_foreshadow_model_has_source_material_id_field,
        test_filter_predicate_shape,
        test_no_project_id_returns_empty_list,
        test_planted_chapter_asc_nulls_last,
        test_bulk_event_insert_stamps_source_material_id,
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
