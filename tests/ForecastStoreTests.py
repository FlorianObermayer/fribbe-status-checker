import os
from datetime import date

import pytest

from app.services.ForecastStore import MAX_TOKENS_PER_DATE, ForecastStore

TOKEN_A = "aaaaaaaa-aaaa-4aaa-aaaa-aaaaaaaaaaaa"
TOKEN_B = "bbbbbbbb-bbbb-4bbb-bbbb-bbbbbbbbbbbb"  # noqa: S105
TOKEN_C = "cccccccc-cccc-4ccc-cccc-cccccccccccc"  # noqa: S105
DATE_1 = date(2026, 4, 3)
DATE_2 = date(2026, 4, 4)


@pytest.fixture
def store(tmp_path: str) -> ForecastStore:
    path = os.path.join(str(tmp_path), "forecasts.json")
    return ForecastStore(path)


# ---------------------------------------------------------------------------
# count / has on unknown date
# ---------------------------------------------------------------------------


def test_count_unknown_date_returns_zero(store: ForecastStore):
    assert store.count(DATE_1) == 0


def test_has_unknown_date_returns_false(store: ForecastStore):
    assert store.has(DATE_1, TOKEN_A) is False


# ---------------------------------------------------------------------------
# add
# ---------------------------------------------------------------------------


def test_add_increments_count(store: ForecastStore):
    store.add(DATE_1, TOKEN_A)
    assert store.count(DATE_1) == 1


def test_add_sets_has_true(store: ForecastStore):
    store.add(DATE_1, TOKEN_A)
    assert store.has(DATE_1, TOKEN_A) is True


def test_add_same_token_twice_is_idempotent(store: ForecastStore):
    store.add(DATE_1, TOKEN_A)
    store.add(DATE_1, TOKEN_A)
    assert store.count(DATE_1) == 1


def test_add_multiple_distinct_tokens(store: ForecastStore):
    store.add(DATE_1, TOKEN_A)
    store.add(DATE_1, TOKEN_B)
    store.add(DATE_1, TOKEN_C)
    assert store.count(DATE_1) == 3


def test_add_does_not_affect_other_dates(store: ForecastStore):
    store.add(DATE_1, TOKEN_A)
    assert store.count(DATE_2) == 0
    assert store.has(DATE_2, TOKEN_A) is False


# ---------------------------------------------------------------------------
# remove
# ---------------------------------------------------------------------------


def test_remove_decrements_count(store: ForecastStore):
    store.add(DATE_1, TOKEN_A)
    store.remove(DATE_1, TOKEN_A)
    assert store.count(DATE_1) == 0


def test_remove_clears_has(store: ForecastStore):
    store.add(DATE_1, TOKEN_A)
    store.remove(DATE_1, TOKEN_A)
    assert store.has(DATE_1, TOKEN_A) is False


def test_remove_nonexistent_token_is_noop(store: ForecastStore):
    store.add(DATE_1, TOKEN_A)
    store.remove(DATE_1, TOKEN_B)
    assert store.count(DATE_1) == 1


def test_remove_unknown_date_is_noop(store: ForecastStore):
    store.remove(DATE_1, TOKEN_A)
    assert store.count(DATE_1) == 0


def test_remove_only_affects_target_token(store: ForecastStore):
    store.add(DATE_1, TOKEN_A)
    store.add(DATE_1, TOKEN_B)
    store.remove(DATE_1, TOKEN_A)
    assert store.has(DATE_1, TOKEN_A) is False
    assert store.has(DATE_1, TOKEN_B) is True
    assert store.count(DATE_1) == 1


# ---------------------------------------------------------------------------
# max tokens cap
# ---------------------------------------------------------------------------


def test_max_tokens_per_date_respected(store: ForecastStore):
    for i in range(MAX_TOKENS_PER_DATE + 1):
        token = f"{i:08x}-0000-4000-a000-000000000000"
        store.add(DATE_1, token)
    assert store.count(DATE_1) == MAX_TOKENS_PER_DATE


# ---------------------------------------------------------------------------
# round-trip persistence
# ---------------------------------------------------------------------------


def test_round_trip_persistence(tmp_path: str):
    path = os.path.join(str(tmp_path), "forecasts.json")
    store1 = ForecastStore(path)
    store1.add(DATE_1, TOKEN_A)
    store1.add(DATE_1, TOKEN_B)
    store1.add(DATE_2, TOKEN_C)

    store2 = ForecastStore(path)
    assert store2.count(DATE_1) == 2
    assert store2.has(DATE_1, TOKEN_A) is True
    assert store2.has(DATE_1, TOKEN_B) is True
    assert store2.count(DATE_2) == 1
    assert store2.has(DATE_2, TOKEN_C) is True


def test_missing_file_starts_empty(tmp_path: str):
    path = os.path.join(str(tmp_path), "nonexistent.json")
    store = ForecastStore(path)
    assert store.count(DATE_1) == 0
