"""Unit tests for app/db.py — schema creation and upsert operations."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Helpers to wire a temp DATABASE_URL into app.env before importing app.db
# ---------------------------------------------------------------------------


@pytest.fixture()
def db_url(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    """Return a sqlite:/// URL pointing to a temp directory and patch env."""
    url = f"sqlite:///{tmp_path}/test_fribbe.db"
    monkeypatch.setenv("DATABASE_URL", url)
    # Re-run env.load() so DATABASE_URL is picked up by app.env globals.
    import app.env as env

    env.load()
    return url


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_get_connection_returns_sqlite_connection(db_url: str) -> None:
    from app.db import get_connection

    conn = get_connection()
    try:
        assert isinstance(conn, sqlite3.Connection)
    finally:
        conn.close()


def test_get_connection_enables_wal_mode(db_url: str) -> None:
    from app.db import get_connection

    with get_connection() as conn:
        row = conn.execute("PRAGMA journal_mode").fetchone()
        assert row[0] == "wal"


def test_get_connection_sets_busy_timeout(db_url: str) -> None:
    from app.db import get_connection

    with get_connection() as conn:
        row = conn.execute("PRAGMA busy_timeout").fetchone()
        assert int(row[0]) == 5000


def test_get_connection_creates_parent_dirs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    nested = tmp_path / "a" / "b" / "c"
    url = f"sqlite:///{nested}/fribbe.db"
    monkeypatch.setenv("DATABASE_URL", url)
    import app.env as env

    env.load()

    from app.db import get_connection

    with get_connection() as conn:
        conn.execute("SELECT 1")
    assert (nested / "fribbe.db").exists()


def test_init_db_creates_all_tables(db_url: str) -> None:
    from app.db import get_connection, init_db

    init_db()

    expected_tables = {
        "occupancy_records",
        "weather_records",
        "tournament_events",
        "forecast_results",
    }

    with get_connection() as conn:
        rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        actual_tables = {row[0] for row in rows}

    assert expected_tables <= actual_tables


def test_init_db_creates_indexes(db_url: str) -> None:
    from app.db import get_connection, init_db

    init_db()

    expected_indexes = {
        "idx_occupancy_records_timestamp",
        "idx_weather_records_timestamp_is_forecast",
        "idx_tournament_events_date",
    }

    with get_connection() as conn:
        rows = conn.execute("SELECT name FROM sqlite_master WHERE type='index'").fetchall()
        actual_indexes = {row[0] for row in rows}

    assert expected_indexes <= actual_indexes


def test_init_db_is_idempotent(db_url: str) -> None:
    from app.db import init_db

    init_db()
    init_db()  # second call must not raise


# ---------------------------------------------------------------------------
# occupancy_records upserts
# ---------------------------------------------------------------------------


def test_occupancy_records_insert_and_query(db_url: str) -> None:
    from app.db import get_connection, init_db

    init_db()

    ts = "2025-07-15T14:00:00Z"
    with get_connection() as conn:
        conn.execute("INSERT INTO occupancy_records (timestamp, count) VALUES (?, ?)", (ts, 5))

    with get_connection() as conn:
        row = conn.execute("SELECT timestamp, count FROM occupancy_records WHERE timestamp = ?", (ts,)).fetchone()

    assert row is not None
    assert row["timestamp"] == ts
    assert row["count"] == 5


def test_occupancy_records_unique_constraint(db_url: str) -> None:
    from app.db import get_connection, init_db

    init_db()

    ts = "2025-07-15T15:00:00Z"
    with get_connection() as conn:
        conn.execute("INSERT INTO occupancy_records (timestamp, count) VALUES (?, ?)", (ts, 3))
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("INSERT INTO occupancy_records (timestamp, count) VALUES (?, ?)", (ts, 7))


def test_occupancy_records_insert_or_replace(db_url: str) -> None:
    from app.db import get_connection, init_db

    init_db()

    ts = "2025-07-15T16:00:00Z"
    with get_connection() as conn:
        conn.execute("INSERT INTO occupancy_records (timestamp, count) VALUES (?, ?)", (ts, 2))
        conn.execute("INSERT OR REPLACE INTO occupancy_records (timestamp, count) VALUES (?, ?)", (ts, 9))

    with get_connection() as conn:
        rows = conn.execute("SELECT count FROM occupancy_records WHERE timestamp = ?", (ts,)).fetchall()

    assert len(rows) == 1
    assert rows[0]["count"] == 9


def test_occupancy_records_insert_or_ignore(db_url: str) -> None:
    from app.db import get_connection, init_db

    init_db()

    ts = "2025-07-15T17:00:00Z"
    with get_connection() as conn:
        conn.execute("INSERT INTO occupancy_records (timestamp, count) VALUES (?, ?)", (ts, 4))
        conn.execute("INSERT OR IGNORE INTO occupancy_records (timestamp, count) VALUES (?, ?)", (ts, 99))

    with get_connection() as conn:
        row = conn.execute("SELECT count FROM occupancy_records WHERE timestamp = ?", (ts,)).fetchone()

    assert row["count"] == 4  # original value preserved


# ---------------------------------------------------------------------------
# weather_records upserts
# ---------------------------------------------------------------------------


def test_weather_records_insert_and_query(db_url: str) -> None:
    from app.db import get_connection, init_db

    init_db()

    ts = "2025-07-15T14:00:00Z"
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO weather_records
               (timestamp, temp_c, precipitation_mm, wind_kph, cloud_cover_pct, weather_code, is_forecast)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (ts, 22.5, 0.0, 15.0, 30, 800, 0),
        )

    with get_connection() as conn:
        row = conn.execute("SELECT * FROM weather_records WHERE timestamp = ?", (ts,)).fetchone()

    assert row is not None
    assert row["temp_c"] == pytest.approx(22.5)
    assert row["is_forecast"] == 0


def test_weather_records_allows_forecast_and_actual_for_same_timestamp(db_url: str) -> None:
    from app.db import get_connection, init_db

    init_db()

    ts = "2025-07-15T18:00:00Z"
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO weather_records (timestamp, temp_c, is_forecast) VALUES (?, ?, ?)",
            (ts, 20.0, 0),
        )
        conn.execute(
            "INSERT INTO weather_records (timestamp, temp_c, is_forecast) VALUES (?, ?, ?)",
            (ts, 21.0, 1),
        )

    with get_connection() as conn:
        rows = conn.execute("SELECT count(*) AS n FROM weather_records WHERE timestamp = ?", (ts,)).fetchone()

    assert rows["n"] == 2


def test_weather_records_unique_constraint(db_url: str) -> None:
    from app.db import get_connection, init_db

    init_db()

    ts = "2025-07-15T19:00:00Z"
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO weather_records (timestamp, temp_c, is_forecast) VALUES (?, ?, ?)",
            (ts, 18.0, 1),
        )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO weather_records (timestamp, temp_c, is_forecast) VALUES (?, ?, ?)",
                (ts, 19.0, 1),
            )


# ---------------------------------------------------------------------------
# tournament_events upserts
# ---------------------------------------------------------------------------


def test_tournament_events_insert_and_query(db_url: str) -> None:
    from app.db import get_connection, init_db

    init_db()

    with get_connection() as conn:
        conn.execute(
            """INSERT INTO tournament_events (name, date, location_type, source)
               VALUES (?, ?, ?, ?)""",
            ("Summer Cup", "2025-07-20", "on_site", "manual"),
        )

    with get_connection() as conn:
        row = conn.execute("SELECT * FROM tournament_events WHERE name = ?", ("Summer Cup",)).fetchone()

    assert row is not None
    assert row["date"] == "2025-07-20"
    assert row["location_type"] == "on_site"


def test_tournament_events_unique_constraint(db_url: str) -> None:
    from app.db import get_connection, init_db

    init_db()

    with get_connection() as conn:
        conn.execute(
            "INSERT INTO tournament_events (name, date, location_type, source) VALUES (?, ?, ?, ?)",
            ("Beach Open", "2025-08-01", "on_site", "bvv"),
        )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO tournament_events (name, date, location_type, source) VALUES (?, ?, ?, ?)",
                ("Beach Open", "2025-08-01", "off_site", "bvv"),
            )


# ---------------------------------------------------------------------------
# forecast_results upserts
# ---------------------------------------------------------------------------


def test_forecast_results_insert_and_query(db_url: str) -> None:
    from app.db import get_connection, init_db

    init_db()

    with get_connection() as conn:
        conn.execute(
            """INSERT INTO forecast_results (date, bucket, level, model_version)
               VALUES (?, ?, ?, ?)""",
            ("2025-07-20", "afternoon", "high", "v1"),
        )

    with get_connection() as conn:
        row = conn.execute("SELECT * FROM forecast_results WHERE date = ?", ("2025-07-20",)).fetchone()

    assert row is not None
    assert row["bucket"] == "afternoon"
    assert row["level"] == "high"


def test_forecast_results_unique_constraint(db_url: str) -> None:
    from app.db import get_connection, init_db

    init_db()

    with get_connection() as conn:
        conn.execute(
            "INSERT INTO forecast_results (date, bucket, level, model_version) VALUES (?, ?, ?, ?)",
            ("2025-07-21", "morning", "low", "v1"),
        )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO forecast_results (date, bucket, level, model_version) VALUES (?, ?, ?, ?)",
                ("2025-07-21", "morning", "high", "v2"),
            )
