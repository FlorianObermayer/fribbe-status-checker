"""One-shot migration: import existing JSON snapshots into occupancy_records.

Usage (from the project root):

    uv run migrate-json-to-db

Or directly:

    python -m scripts.migrate_json_to_db

The script reads ``LOCAL_DATA_PATH`` from the environment (via ``app.env``),
looks for any ``*.json`` files that contain a mapping of ISO-8601 timestamps
to integer device counts, and upserts each entry into the ``occupancy_records``
table.  It is safe to run multiple times - duplicate timestamps are silently
ignored thanks to ``INSERT OR IGNORE``.

Expected JSON shape (produced by PersistentDict[int])::

    {
        "2025-07-15T14:00:00+02:00": 3,
        "2025-07-15T15:00:00+02:00": 1
    }

Only files whose values are entirely integers are migrated; all others are
skipped with a warning.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path

# Ensure the project root is on the path so ``import app`` works when the
# script is executed directly (outside of ``uv run``).
sys.path.insert(0, str(Path(__file__).parent.parent))

import app.env as env
from app.db import get_connection, init_db

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def _to_utc_iso(ts_str: str) -> str | None:
    """Parse an ISO-8601 timestamp and return it normalised to UTC.

    Returns ``None`` if the string cannot be parsed.
    """
    try:
        dt = datetime.fromisoformat(ts_str)
        if dt.tzinfo is None:
            # Treat naive timestamps as UTC.
            dt = dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return None


def _migrate_file(conn: sqlite3.Connection, path: Path) -> int:
    """Migrate a single JSON file.  Returns the number of rows inserted."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Skipping %s — could not read/parse: %s", path, exc)
        return 0

    if not isinstance(raw, dict):
        logger.debug("Skipping %s — not a JSON object", path)
        return 0

    rows: list[tuple[str, int]] = []
    for key, value in raw.items():
        if type(value) is not int:
            logger.debug("Skipping %s — non-integer value for key %r", path, key)
            return 0
        utc_ts = _to_utc_iso(key)
        if utc_ts is None:
            logger.debug("Skipping %s — key %r is not a valid ISO-8601 timestamp", path, key)
            return 0
        rows.append((utc_ts, value))

    if not rows:
        return 0

    inserted = 0
    for utc_ts, count in rows:
        try:
            conn.execute(
                "INSERT OR IGNORE INTO occupancy_records (timestamp, count) VALUES (?, ?)",
                (utc_ts, count),
            )
            rows_affected: int = conn.execute("SELECT changes()").fetchone()[0]
            if rows_affected > 0:
                inserted += 1
        except sqlite3.Error as exc:
            logger.warning("Failed to insert %s / %s: %s", path, utc_ts, exc)

    return inserted


def main() -> None:
    env.validate()
    init_db()

    data_path = Path(env.LOCAL_DATA_PATH)
    if not data_path.exists():
        logger.error("LOCAL_DATA_PATH does not exist: %s", data_path)
        sys.exit(1)

    json_files = list(data_path.rglob("*.json"))
    if not json_files:
        logger.info("No JSON files found in %s — nothing to migrate", data_path)
        return

    total_inserted = 0
    with get_connection() as conn:
        for json_file in json_files:
            n = _migrate_file(conn, json_file)
            if n:
                logger.info("Migrated %d row(s) from %s", n, json_file)
            total_inserted += n

    logger.info("Migration complete — %d occupancy_records row(s) inserted", total_inserted)


if __name__ == "__main__":
    main()
