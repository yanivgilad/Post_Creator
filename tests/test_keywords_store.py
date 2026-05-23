from __future__ import annotations

import pytest

from article_writer.storage.sqlite_store import SQLiteStore, TIER_WEIGHTS


@pytest.fixture
def store(settings) -> SQLiteStore:
    s = SQLiteStore(settings)
    s.init_db()
    return s


def test_seed_inserts_at_medium_on_empty_db(store):
    seed = ["alpha", "beta", "GAMMA"]
    inserted = store.seed_keywords_if_empty(seed)
    assert inserted == 3

    rows = store.list_keywords()
    assert [r["keyword"] for r in rows] == ["alpha", "beta", "gamma"]
    assert all(r["tier"] == "MEDIUM" for r in rows)
    assert all(r["weight"] == TIER_WEIGHTS["MEDIUM"] for r in rows)


def test_seed_is_idempotent_and_preserves_edits(store):
    store.seed_keywords_if_empty(["alpha", "beta"])
    rows = store.list_keywords()
    target_id = next(r["id"] for r in rows if r["keyword"] == "alpha")

    updated = store.update_keyword_tier(target_id, "HIGH")
    assert updated is not None
    assert updated["tier"] == "HIGH"

    # Re-seed should be a no-op
    second = store.seed_keywords_if_empty(["alpha", "beta", "gamma"])
    assert second == 0

    rows_after = store.list_keywords()
    assert len(rows_after) == 2
    assert next(r for r in rows_after if r["keyword"] == "alpha")["tier"] == "HIGH"


def test_seed_deduplicates_and_normalizes(store):
    inserted = store.seed_keywords_if_empty(["Alpha", "alpha", "  alpha  ", "beta"])
    assert inserted == 2


def test_create_keyword_rejects_duplicates_case_insensitive(store):
    store.create_keyword("alpha", "LOW")
    with pytest.raises(ValueError):
        store.create_keyword("ALPHA", "HIGH")


def test_create_keyword_rejects_invalid_tier(store):
    with pytest.raises(ValueError):
        store.create_keyword("alpha", "URGENT")


def test_update_and_delete_missing_ids(store):
    assert store.update_keyword_tier(999, "HIGH") is None
    assert store.delete_keyword(999) is False


def test_list_order_high_then_medium_then_low(store):
    store.create_keyword("a-low", "LOW")
    store.create_keyword("b-high", "HIGH")
    store.create_keyword("c-medium", "MEDIUM")
    store.create_keyword("d-high", "HIGH")

    order = [r["keyword"] for r in store.list_keywords()]
    assert order == ["b-high", "d-high", "c-medium", "a-low"]


def test_list_keywords_for_matching_returns_tuples(store):
    store.create_keyword("alpha", "HIGH")
    store.create_keyword("beta", "LOW")
    matching = dict(store.list_keywords_for_matching())
    assert matching == {"alpha": "HIGH", "beta": "LOW"}
