"""SQLite database connection helper and schema management.

Provides get_connection() for WAL-enabled connections and create_schema() to
initialise all tables via CREATE TABLE IF NOT EXISTS.
"""

import sqlite3
from pathlib import Path


def _parse_db_path(database_url: str) -> str:
    """Extract the file-system path from a sqlite:/// URL."""
    if database_url.startswith("sqlite:///"):
        return database_url[len("sqlite:///") :]
    return database_url


def get_connection(database_url: str) -> sqlite3.Connection:
    """Return a sqlite3 connection with WAL mode and busy-timeout configured.

    Args:
        database_url: A ``sqlite:///path/to/file.db`` URL or a plain file path.

    Returns:
        An open :class:`sqlite3.Connection` with WAL journal mode and a 5-second
        busy timeout applied.  Row factory is set to :class:`sqlite3.Row` so
        columns can be accessed by name.
    """
    db_path = _parse_db_path(database_url)
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def create_schema(conn: sqlite3.Connection) -> None:
    """Create all application tables if they do not already exist.

    Idempotent — safe to call on every startup.
    """
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS occupancy_records (
            id          INTEGER PRIMARY KEY,
            timestamp   TEXT NOT NULL,
            count       INTEGER NOT NULL,
            created_at  TEXT NOT NULL
        );
        CREATE UNIQUE INDEX IF NOT EXISTS uq_occupancy_timestamp
            ON occupancy_records (timestamp);
        CREATE INDEX IF NOT EXISTS idx_occupancy_timestamp
            ON occupancy_records (timestamp);

        CREATE TABLE IF NOT EXISTS weather_records (
            id                  INTEGER PRIMARY KEY,
            timestamp           TEXT NOT NULL,
            temp_c              REAL,
            precipitation_mm    REAL,
            wind_kph            REAL,
            cloud_cover_pct     INTEGER,
            weather_code        INTEGER,
            is_forecast         INTEGER NOT NULL DEFAULT 0,
            created_at          TEXT NOT NULL
        );
        CREATE UNIQUE INDEX IF NOT EXISTS uq_weather_timestamp_forecast
            ON weather_records (timestamp, is_forecast);
        CREATE INDEX IF NOT EXISTS idx_weather_timestamp
            ON weather_records (timestamp);

        CREATE TABLE IF NOT EXISTS tournament_events (
            id                  INTEGER PRIMARY KEY,
            name                TEXT NOT NULL,
            date                TEXT NOT NULL,
            start_time          TEXT,
            end_time            TEXT,
            location_type       TEXT NOT NULL,
            participant_count   INTEGER,
            source              TEXT NOT NULL,
            created_at          TEXT NOT NULL
        );
        CREATE UNIQUE INDEX IF NOT EXISTS uq_tournament_name_date_source
            ON tournament_events (name, date, source);

        CREATE TABLE IF NOT EXISTS forecast_results (
            id              INTEGER PRIMARY KEY,
            date            TEXT NOT NULL,
            bucket          TEXT NOT NULL,
            level           TEXT NOT NULL,
            confidence      REAL,
            model_version   TEXT NOT NULL,
            created_at      TEXT NOT NULL
        );
        CREATE UNIQUE INDEX IF NOT EXISTS uq_forecast_date_bucket
            ON forecast_results (date, bucket);
        CREATE INDEX IF NOT EXISTS idx_forecast_date
            ON forecast_results (date);
    """)
    conn.commit()


def upsert_occupancy_record(conn: sqlite3.Connection, timestamp: str, count: int, created_at: str) -> None:
    """Insert or replace an occupancy record (upsert by timestamp)."""
    conn.execute(
        """
        INSERT OR REPLACE INTO occupancy_records (timestamp, count, created_at)
        VALUES (?, ?, ?)
        """,
        (timestamp, count, created_at),
    )
    conn.commit()


def upsert_weather_record(
    conn: sqlite3.Connection,
    timestamp: str,
    temp_c: float | None,
    precipitation_mm: float | None,
    wind_kph: float | None,
    cloud_cover_pct: int | None,
    weather_code: int | None,
    is_forecast: int,
    created_at: str,
) -> None:
    """Insert or replace a weather record (upsert by timestamp + is_forecast)."""
    conn.execute(
        """
        INSERT OR REPLACE INTO weather_records
            (timestamp, temp_c, precipitation_mm, wind_kph, cloud_cover_pct, weather_code, is_forecast, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (timestamp, temp_c, precipitation_mm, wind_kph, cloud_cover_pct, weather_code, is_forecast, created_at),
    )
    conn.commit()
