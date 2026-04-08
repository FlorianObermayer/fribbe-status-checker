"""DB service layer for occupancy_records.

Provides typed read/write access to the ``occupancy_records`` table via plain
``sqlite3``.  All timestamps are stored and returned as UTC ISO 8601 strings.
Each incoming datetime is floored to the 1-hour bucket start so that repeated
polls within the same hour converge to a single row (``INSERT OR REPLACE``).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from app.db import get_connection


@dataclass
class OccupancyRecord:
    """A single hourly device-count snapshot."""

    timestamp: str
    count: int
    created_at: str


def _to_hour_bucket(dt: datetime) -> str:
    """Floor *dt* to the hour and return a UTC ISO 8601 string."""
    utc = dt.astimezone(UTC)
    bucket = utc.replace(minute=0, second=0, microsecond=0)
    return bucket.strftime("%Y-%m-%dT%H:%M:%SZ")


class OccupancyRecordService:
    """Read/write service for the ``occupancy_records`` table."""

    def upsert(self, timestamp: datetime, count: int) -> None:
        """Upsert a device-count record for the 1-hour bucket containing *timestamp*.

        If a row for the same bucket already exists it is replaced so that the
        latest observed count within each hour wins.
        """
        ts_str = _to_hour_bucket(timestamp)
        with get_connection() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO occupancy_records (timestamp, count) VALUES (?, ?)",
                (ts_str, count),
            )

    def get_recent(self, limit: int = 168) -> list[OccupancyRecord]:
        """Return the *limit* most recent records ordered newest-first.

        The default of 168 covers the last 7 days (7 x 24 h).
        """
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT timestamp, count, created_at FROM occupancy_records ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [
            OccupancyRecord(timestamp=row["timestamp"], count=row["count"], created_at=row["created_at"])
            for row in rows
        ]

    def get_by_date_range(self, start: str, end: str) -> list[OccupancyRecord]:
        """Return records whose bucket timestamp falls within [*start*, *end*] (inclusive).

        Both *start* and *end* should be UTC ISO 8601 strings
        (e.g. ``"2025-07-01T00:00:00Z"`` / ``"2025-07-31T23:00:00Z"``).
        Results are ordered oldest-first.
        """
        with get_connection() as conn:
            rows = conn.execute(
                """SELECT timestamp, count, created_at FROM occupancy_records
                   WHERE timestamp >= ? AND timestamp <= ?
                   ORDER BY timestamp""",
                (start, end),
            ).fetchall()
        return [
            OccupancyRecord(timestamp=row["timestamp"], count=row["count"], created_at=row["created_at"])
            for row in rows
        ]
