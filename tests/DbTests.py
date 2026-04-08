"""Unit tests for app/db.py — schema creation and upsert operations."""

import sqlite3
import tempfile
from pathlib import Path

import pytest

from app.db import (
    create_schema,
    get_connection,
    upsert_occupancy_record,
    upsert_weather_record,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_conn(tmp_path: Path) -> sqlite3.Connection:
    db_url = f"sqlite:///{tmp_path / 'test.db'}"
    conn = get_connection(db_url)
    create_schema(conn)
    return conn


# ---------------------------------------------------------------------------
# get_connection
# ---------------------------------------------------------------------------


def test_get_connection_creates_file():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = str(Path(tmpdir) / "sub" / "test.db")
        conn = get_connection(f"sqlite:///{db_path}")
        conn.close()
        assert Path(db_path).exists()


def test_get_connection_wal_mode():
    with tempfile.TemporaryDirectory() as tmpdir:
        conn = get_connection(f"sqlite:///{tmpdir}/wal.db")
        row = conn.execute("PRAGMA journal_mode").fetchone()
        assert row[0] == "wal"
        conn.close()


def test_get_connection_busy_timeout():
    with tempfile.TemporaryDirectory() as tmpdir:
        conn = get_connection(f"sqlite:///{tmpdir}/bt.db")
        row = conn.execute("PRAGMA busy_timeout").fetchone()
        assert row[0] == 5000
        conn.close()


def test_get_connection_row_factory():
    with tempfile.TemporaryDirectory() as tmpdir:
        conn = get_connection(f"sqlite:///{tmpdir}/rf.db")
        conn.execute("CREATE TABLE t (a INTEGER, b TEXT)")
        conn.execute("INSERT INTO t VALUES (1, 'hello')")
        row = conn.execute("SELECT a, b FROM t").fetchone()
        assert row["a"] == 1
        assert row["b"] == "hello"
        conn.close()


def test_get_connection_plain_path():
    """get_connection() also accepts a plain file path (no sqlite:/// prefix)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = str(Path(tmpdir) / "plain.db")
        conn = get_connection(db_path)
        conn.close()
        assert Path(db_path).exists()


# ---------------------------------------------------------------------------
# create_schema — idempotency
# ---------------------------------------------------------------------------


def test_create_schema_idempotent(tmp_path: Path):
    conn = _make_conn(tmp_path)
    # Calling create_schema a second time must not raise.
    create_schema(conn)
    conn.close()


def test_create_schema_tables_exist(tmp_path: Path):
    conn = _make_conn(tmp_path)
    tables = {row["name"] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    assert "occupancy_records" in tables
    assert "weather_records" in tables
    assert "tournament_events" in tables
    assert "forecast_results" in tables
    conn.close()


def test_create_schema_indexes_exist(tmp_path: Path):
    conn = _make_conn(tmp_path)
    indexes = {row["name"] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='index'").fetchall()}
    assert "uq_occupancy_timestamp" in indexes
    assert "idx_occupancy_timestamp" in indexes
    assert "uq_weather_timestamp_forecast" in indexes
    assert "idx_weather_timestamp" in indexes
    assert "uq_tournament_name_date_source" in indexes
    assert "uq_forecast_date_bucket" in indexes
    assert "idx_forecast_date" in indexes
    conn.close()


# ---------------------------------------------------------------------------
# occupancy_records upsert
# ---------------------------------------------------------------------------


def test_upsert_occupancy_record_insert(tmp_path: Path):
    conn = _make_conn(tmp_path)
    upsert_occupancy_record(conn, "2025-07-15T14:00:00Z", 5, "2025-07-15T14:05:00Z")
    row = conn.execute("SELECT timestamp, count FROM occupancy_records").fetchone()
    assert row["timestamp"] == "2025-07-15T14:00:00Z"
    assert row["count"] == 5
    conn.close()


def test_upsert_occupancy_record_replace(tmp_path: Path):
    conn = _make_conn(tmp_path)
    upsert_occupancy_record(conn, "2025-07-15T14:00:00Z", 5, "2025-07-15T14:05:00Z")
    upsert_occupancy_record(conn, "2025-07-15T14:00:00Z", 10, "2025-07-15T14:10:00Z")
    rows = conn.execute("SELECT count FROM occupancy_records WHERE timestamp='2025-07-15T14:00:00Z'").fetchall()
    assert len(rows) == 1
    assert rows[0]["count"] == 10
    conn.close()


def test_upsert_occupancy_record_multiple(tmp_path: Path):
    conn = _make_conn(tmp_path)
    upsert_occupancy_record(conn, "2025-07-15T13:00:00Z", 3, "2025-07-15T14:00:00Z")
    upsert_occupancy_record(conn, "2025-07-15T14:00:00Z", 7, "2025-07-15T14:00:00Z")
    rows = conn.execute("SELECT count(*) as n FROM occupancy_records").fetchone()
    assert rows["n"] == 2
    conn.close()


def test_upsert_occupancy_unique_constraint(tmp_path: Path):
    """Duplicate timestamp without using helper should raise IntegrityError."""
    conn = _make_conn(tmp_path)
    conn.execute(
        "INSERT INTO occupancy_records (timestamp, count, created_at) VALUES (?, ?, ?)",
        ("2025-07-15T14:00:00Z", 1, "2025-07-15T14:00:00Z"),
    )
    conn.commit()
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO occupancy_records (timestamp, count, created_at) VALUES (?, ?, ?)",
            ("2025-07-15T14:00:00Z", 2, "2025-07-15T14:00:00Z"),
        )
    conn.close()


# ---------------------------------------------------------------------------
# weather_records upsert
# ---------------------------------------------------------------------------


def test_upsert_weather_record_insert(tmp_path: Path):
    conn = _make_conn(tmp_path)
    upsert_weather_record(conn, "2025-07-15T14:00:00Z", 28.5, 0.0, 15.0, 20, 800, 0, "2025-07-15T14:05:00Z")
    row = conn.execute("SELECT * FROM weather_records").fetchone()
    assert row["timestamp"] == "2025-07-15T14:00:00Z"
    assert abs(row["temp_c"] - 28.5) < 1e-9
    assert row["is_forecast"] == 0
    conn.close()


def test_upsert_weather_record_replace(tmp_path: Path):
    conn = _make_conn(tmp_path)
    upsert_weather_record(conn, "2025-07-15T14:00:00Z", 20.0, 0.0, 10.0, 50, 802, 0, "2025-07-15T14:00:00Z")
    upsert_weather_record(conn, "2025-07-15T14:00:00Z", 25.0, 1.0, 12.0, 60, 500, 0, "2025-07-15T14:05:00Z")
    rows = conn.execute(
        "SELECT temp_c FROM weather_records WHERE timestamp='2025-07-15T14:00:00Z' AND is_forecast=0"
    ).fetchall()
    assert len(rows) == 1
    assert abs(rows[0]["temp_c"] - 25.0) < 1e-9
    conn.close()


def test_upsert_weather_record_forecast_and_actual_coexist(tmp_path: Path):
    conn = _make_conn(tmp_path)
    upsert_weather_record(conn, "2025-07-15T14:00:00Z", 20.0, 0.0, 10.0, 50, 802, 1, "2025-07-15T13:00:00Z")
    upsert_weather_record(conn, "2025-07-15T14:00:00Z", 22.0, 0.2, 11.0, 55, 500, 0, "2025-07-15T14:05:00Z")
    rows = conn.execute("SELECT is_forecast FROM weather_records ORDER BY is_forecast").fetchall()
    assert len(rows) == 2
    assert rows[0]["is_forecast"] == 0
    assert rows[1]["is_forecast"] == 1
    conn.close()


def test_upsert_weather_record_nullable_fields(tmp_path: Path):
    conn = _make_conn(tmp_path)
    upsert_weather_record(conn, "2025-07-15T14:00:00Z", None, None, None, None, None, 0, "2025-07-15T14:05:00Z")
    row = conn.execute("SELECT * FROM weather_records").fetchone()
    assert row["temp_c"] is None
    assert row["precipitation_mm"] is None
    conn.close()
