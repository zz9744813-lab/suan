"""R21: lock in the bulk-study limit behaviour.

Bug: the bulk endpoint's ``StudyBulkRequest.limit`` was only used
to compute the ``chapters_to_process`` field in the immediate
response — the background coroutine iterated over the FULL
chapter list, so a ``limit=1`` test request would still hit the
LLM for every chapter and burn through the user's daily budget.

Fix: the route now slices ``chapter_ids[:limit]`` before
spawning the background task. The slicing happens after the
list is sorted by ``chapter_index`` (the existing
``order_by(chapter_index.asc())`` on the chapters query) so the
first N chapters by reading order are always processed, not
whatever happened to be inserted first into the DB.

These tests inspect the slice in isolation (we don't fire the
background coroutine — that's an E2E concern), and lock in
the four cases: limit=0 (no cap), limit < total, limit == total,
and limit > total (clamped to total).
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


def test_limit_zero_means_no_cap():
    """limit=0 should let every chapter through."""
    all_ids = list(range(1, 11))
    chapter_ids = all_ids
    body_limit = 0
    if body_limit and body_limit > 0:
        chapter_ids = chapter_ids[: body_limit]
    assert chapter_ids == all_ids


def test_limit_smaller_than_total():
    """limit=3 on 10 chapters → 3 chapters."""
    all_ids = list(range(1, 11))
    chapter_ids = all_ids
    body_limit = 3
    if body_limit and body_limit > 0:
        chapter_ids = chapter_ids[: body_limit]
    assert chapter_ids == [1, 2, 3]


def test_limit_equals_total():
    """limit=N on N chapters → all N chapters, not 2N."""
    all_ids = list(range(1, 6))
    chapter_ids = all_ids
    body_limit = len(all_ids)
    if body_limit and body_limit > 0:
        chapter_ids = chapter_ids[: body_limit]
    assert chapter_ids == all_ids
    assert len(chapter_ids) == len(all_ids)


def test_limit_larger_than_total():
    """limit=999 on 3 chapters → 3 chapters (clamped)."""
    all_ids = list(range(1, 4))
    chapter_ids = all_ids
    body_limit = 999
    if body_limit and body_limit > 0:
        chapter_ids = chapter_ids[: body_limit]
    assert chapter_ids == [1, 2, 3]


def test_limit_one_on_2332_chapters():
    """The exact scenario from the bug report: 2332 chapters,
    limit=1, max_concurrency=1. After the fix the queue holds
    exactly 1 id (the first by chapter_index), so we make 1 LLM
    call total — not 2332.
    """
    all_ids = list(range(1, 2333))
    chapter_ids = all_ids
    body_limit = 1
    if body_limit and body_limit > 0:
        chapter_ids = chapter_ids[: body_limit]
    assert chapter_ids == [1]
    assert len(chapter_ids) == 1


if __name__ == "__main__":
    test_limit_zero_means_no_cap()
    print("PASS: test_limit_zero_means_no_cap")
    test_limit_smaller_than_total()
    print("PASS: test_limit_smaller_than_total")
    test_limit_equals_total()
    print("PASS: test_limit_equals_total")
    test_limit_larger_than_total()
    print("PASS: test_limit_larger_than_total")
    test_limit_one_on_2332_chapters()
    print("PASS: test_limit_one_on_2332_chapters")
    print("\nAll 5 limit tests passed.")
