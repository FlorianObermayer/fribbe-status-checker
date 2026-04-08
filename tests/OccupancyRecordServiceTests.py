"""Unit tests for app/services/OccupancyRecordService."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Fixture: inject a temp DATABASE_URL before importing OccupancyRecordService
# ---------------------------------------------------------------------------


@pytest.fixture()
def db_url(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    url = f"sqlite:///{tmp_path}/test_occupancy.db"
    monkeypatch.setenv("DATABASE_URL", url)
    import app.env as env

    env.load()
    from app.db import init_db

    init_db()
    return url


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_service():
    from app.services.OccupancyRecordService import OccupancyRecordService

    return OccupancyRecordService()


def _utc(iso: str) -> datetime:
    return datetime.fromisoformat(iso).replace(tzinfo=UTC)


# ---------------------------------------------------------------------------
# upsert
# ---------------------------------------------------------------------------


def test_upsert_inserts_new_record(db_url: str) -> None:
    svc = _make_service()
    ts = _utc("2025-07-15T14:30:00Z")
    svc.upsert(ts, 5)

    records = svc.get_recent(10)
    assert len(records) == 1
    assert records[0].timestamp == "2025-07-15T14:00:00Z"  # floored to hour
    assert records[0].count == 5


def test_upsert_floors_to_hour_bucket(db_url: str) -> None:
    svc = _make_service()
    # Three timestamps in the same hour — should produce a single row
    svc.upsert(_utc("2025-07-15T14:05:00Z"), 1)
    svc.upsert(_utc("2025-07-15T14:33:00Z"), 3)
    svc.upsert(_utc("2025-07-15T14:59:00Z"), 7)

    records = svc.get_recent(10)
    assert len(records) == 1
    assert records[0].timestamp == "2025-07-15T14:00:00Z"
    assert records[0].count == 7  # last upsert wins (INSERT OR REPLACE)


def test_upsert_different_hours_produce_separate_rows(db_url: str) -> None:
    svc = _make_service()
    svc.upsert(_utc("2025-07-15T14:00:00Z"), 2)
    svc.upsert(_utc("2025-07-15T15:00:00Z"), 4)

    records = svc.get_recent(10)
    assert len(records) == 2


def test_upsert_converts_non_utc_timezone_to_utc(db_url: str) -> None:
    from zoneinfo import ZoneInfo

    svc = _make_service()
    berlin = ZoneInfo("Europe/Berlin")
    # 16:30 Berlin (UTC+2) → 14:30 UTC → bucket 14:00 UTC
    ts_berlin = datetime(2025, 7, 15, 16, 30, 0, tzinfo=berlin)
    svc.upsert(ts_berlin, 3)

    records = svc.get_recent(10)
    assert len(records) == 1
    assert records[0].timestamp == "2025-07-15T14:00:00Z"


# ---------------------------------------------------------------------------
# get_recent
# ---------------------------------------------------------------------------


def test_get_recent_returns_newest_first(db_url: str) -> None:
    svc = _make_service()
    for hour in range(5):
        svc.upsert(_utc(f"2025-07-15T{hour:02d}:00:00Z"), hour)

    records = svc.get_recent(5)
    timestamps = [r.timestamp for r in records]
    assert timestamps == sorted(timestamps, reverse=True)


def test_get_recent_respects_limit(db_url: str) -> None:
    svc = _make_service()
    for hour in range(10):
        svc.upsert(_utc(f"2025-07-15T{hour:02d}:00:00Z"), hour)

    records = svc.get_recent(3)
    assert len(records) == 3


def test_get_recent_returns_empty_list_when_no_records(db_url: str) -> None:
    svc = _make_service()
    assert svc.get_recent() == []


# ---------------------------------------------------------------------------
# get_by_date_range
# ---------------------------------------------------------------------------


def test_get_by_date_range_returns_records_in_range(db_url: str) -> None:
    svc = _make_service()
    for hour in range(24):
        svc.upsert(_utc(f"2025-07-15T{hour:02d}:00:00Z"), hour)

    records = svc.get_by_date_range("2025-07-15T06:00:00Z", "2025-07-15T11:00:00Z")
    assert len(records) == 6  # 06, 07, 08, 09, 10, 11
    assert records[0].timestamp == "2025-07-15T06:00:00Z"
    assert records[-1].timestamp == "2025-07-15T11:00:00Z"


def test_get_by_date_range_is_inclusive(db_url: str) -> None:
    svc = _make_service()
    svc.upsert(_utc("2025-07-15T08:00:00Z"), 1)
    svc.upsert(_utc("2025-07-15T09:00:00Z"), 2)
    svc.upsert(_utc("2025-07-15T10:00:00Z"), 3)

    records = svc.get_by_date_range("2025-07-15T08:00:00Z", "2025-07-15T10:00:00Z")
    assert len(records) == 3


def test_get_by_date_range_returns_empty_list_when_no_matches(db_url: str) -> None:
    svc = _make_service()
    svc.upsert(_utc("2025-07-15T08:00:00Z"), 1)

    records = svc.get_by_date_range("2025-07-16T00:00:00Z", "2025-07-16T23:00:00Z")
    assert records == []


def test_get_by_date_range_orders_oldest_first(db_url: str) -> None:
    svc = _make_service()
    for hour in [10, 8, 9]:
        svc.upsert(_utc(f"2025-07-15T{hour:02d}:00:00Z"), hour)

    records = svc.get_by_date_range("2025-07-15T08:00:00Z", "2025-07-15T10:00:00Z")
    timestamps = [r.timestamp for r in records]
    assert timestamps == sorted(timestamps)
