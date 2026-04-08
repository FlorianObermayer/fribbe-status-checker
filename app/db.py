"""SQLite database helpers.

Provides a connection factory with WAL mode and busy-timeout pragmas,
plus a one-time schema initialisation function.

All timestamps are stored as UTC ISO 8601 strings (SQLite has no native
timestamp type). Unique constraints prevent duplicate ingestion; use
``INSERT OR IGNORE`` to skip duplicates silently or ``INSERT OR REPLACE``
to overwrite existing rows with fresh data.
"""

import sqlite3
from pathlib import Path

import app.env as env

# ---------------------------------------------------------------------------
# DDL
# ---------------------------------------------------------------------------

_CREATE_OCCUPANCY_RECORDS = """
CREATE TABLE IF NOT EXISTS occupancy_records (
    id          INTEGER PRIMARY KEY,
    timestamp   TEXT    NOT NULL,
    count       INTEGER NOT NULL,
    created_at  TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    UNIQUE (timestamp)
);
"""

_CREATE_OCCUPANCY_RECORDS_IDX = """
CREATE INDEX IF NOT EXISTS idx_occupancy_records_timestamp
    ON occupancy_records (timestamp);
"""

_CREATE_WEATHER_RECORDS = """
CREATE TABLE IF NOT EXISTS weather_records (
    id                  INTEGER PRIMARY KEY,
    timestamp           TEXT    NOT NULL,
    temp_c              REAL,
    precipitation_mm    REAL,
    wind_kph            REAL,
    cloud_cover_pct     INTEGER,
    weather_code        INTEGER,
    is_forecast         INTEGER NOT NULL DEFAULT 0,
    created_at          TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    UNIQUE (timestamp, is_forecast)
);
"""

_CREATE_WEATHER_RECORDS_IDX = """
CREATE INDEX IF NOT EXISTS idx_weather_records_timestamp
    ON weather_records (timestamp);
"""

_CREATE_TOURNAMENT_EVENTS = """
CREATE TABLE IF NOT EXISTS tournament_events (
    id                INTEGER PRIMARY KEY,
    name              TEXT    NOT NULL,
    date              TEXT    NOT NULL,
    start_time        TEXT,
    end_time          TEXT,
    location_type     TEXT    NOT NULL,
    participant_count INTEGER,
    source            TEXT    NOT NULL,
    created_at        TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    UNIQUE (name, date, source)
);
"""

_CREATE_FORECAST_RESULTS = """
CREATE TABLE IF NOT EXISTS forecast_results (
    id            INTEGER PRIMARY KEY,
    date          TEXT    NOT NULL,
    bucket        TEXT    NOT NULL,
    level         TEXT    NOT NULL,
    confidence    REAL,
    model_version TEXT    NOT NULL,
    created_at    TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    UNIQUE (date, bucket)
);
"""

_CREATE_FORECAST_RESULTS_IDX = """
CREATE INDEX IF NOT EXISTS idx_forecast_results_date
    ON forecast_results (date);
"""

_ALL_DDL: list[str] = [
    _CREATE_OCCUPANCY_RECORDS,
    _CREATE_OCCUPANCY_RECORDS_IDX,
    _CREATE_WEATHER_RECORDS,
    _CREATE_WEATHER_RECORDS_IDX,
    _CREATE_TOURNAMENT_EVENTS,
    _CREATE_FORECAST_RESULTS,
    _CREATE_FORECAST_RESULTS_IDX,
]


# ---------------------------------------------------------------------------
# Connection factory
# ---------------------------------------------------------------------------


def _db_path_from_url(url: str) -> str:
    """Extract the filesystem path from a ``sqlite:///...`` URL."""
    if url.startswith("sqlite:///"):
        return url[len("sqlite:///"):]
    raise ValueError(f"Unsupported DATABASE_URL scheme: {url!r}")


def get_connection() -> sqlite3.Connection:
    """Return a new SQLite connection with WAL mode and busy-timeout applied.

    The caller is responsible for closing the connection (use as a context
    manager or call ``.close()`` explicitly).

    WAL mode allows concurrent reads while a write is in progress, which is
    important for background polling threads writing alongside HTTP handlers
    reading. ``busy_timeout=5000`` prevents immediate ``SQLITE_BUSY`` errors
    under brief write contention.
    """
    db_path = _db_path_from_url(env.DATABASE_URL)
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.row_factory = sqlite3.Row
    return conn


# ---------------------------------------------------------------------------
# Schema initialisation
# ---------------------------------------------------------------------------


def init_db() -> None:
    """Create all tables and indexes if they do not already exist.

    Safe to call multiple times (idempotent).
    """
    with get_connection() as conn:
        for ddl in _ALL_DDL:
            conn.execute(ddl)
