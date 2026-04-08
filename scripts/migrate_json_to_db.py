#!/usr/bin/env python3
"""One-shot migration: import historical occupancy data from JSON files into SQLite.

Usage:
    uv run migrate-json-to-db

The script reads JSON snapshots from LOCAL_DATA_PATH (set via .env.dev or environment
variables) and inserts them into the ``occupancy_records`` table.  Already-existing
rows are replaced (INSERT OR REPLACE) so the script is safe to re-run.

Only files whose names look like ISO 8601 date-prefixed JSON snapshots are processed.
Currently supported format: any ``*.json`` file whose top-level value is a mapping of
ISO 8601 timestamp strings to integer device counts.
"""

import json
import logging
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

# Ensure app package is importable when run directly.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import app.env as env
from app.db import create_schema, get_connection, upsert_occupancy_record

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def _now_utc_iso() -> str:
    return datetime.now(tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _migrate_json_file(conn: sqlite3.Connection, path: Path, dry_run: bool) -> int:
    """Attempt to import a single JSON file as occupancy records.

    Returns the number of rows inserted/replaced.
    """
    try:
        raw: Any = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        logger.warning("Skipping %s — JSON parse error: %s", path, exc)
        return 0

    if not isinstance(raw, dict):
        logger.debug("Skipping %s — not a mapping", path)
        return 0

    mapping = cast(dict[str, Any], raw)
    created_at = _now_utc_iso()
    count = 0
    for key, value in mapping.items():
        # Accept entries where key is an ISO 8601 timestamp and value is int-like.
        if not isinstance(value, (int, float)):
            logger.debug("Skipping key %r in %s — value is not numeric", str(key), path)
            continue
        try:
            # Normalise to UTC ISO 8601 with Z suffix.
            ts = datetime.fromisoformat(str(key).replace("Z", "+00:00"))
            timestamp = ts.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            logger.debug("Skipping key %r in %s — not a parseable timestamp", str(key), path)
            continue

        device_count = int(value)
        if dry_run:
            logger.info("[DRY RUN] Would insert: timestamp=%s count=%d", timestamp, device_count)
        else:
            upsert_occupancy_record(conn, timestamp, device_count, created_at)
        count += 1

    return count


def main() -> None:
    env.validate()

    dry_run = "--dry-run" in sys.argv

    data_path = Path(env.LOCAL_DATA_PATH)
    if not data_path.exists():
        logger.error("LOCAL_DATA_PATH does not exist: %s", data_path)
        sys.exit(1)

    db_url = env.DATABASE_URL
    logger.info("Connecting to database: %s", db_url)
    conn = get_connection(db_url)
    create_schema(conn)

    json_files = sorted(data_path.rglob("*.json"))
    if not json_files:
        logger.info("No JSON files found in %s", data_path)
        return

    total = 0
    for json_file in json_files:
        logger.info("Processing %s", json_file)
        n = _migrate_json_file(conn, json_file, dry_run=dry_run)
        if n:
            logger.info("  -> %d record(s) imported", n)
        total += n

    logger.info("Migration complete. Total records imported: %d", total)
    conn.close()


if __name__ == "__main__":
    main()
