"""Tests for FileSessionStore."""

import hashlib
import os
import time
from pathlib import Path

import pytest

from app.stores.file_session_store import FileSessionStore


@pytest.fixture
def store(tmp_path: Path) -> FileSessionStore:
    return FileSessionStore(str(tmp_path / "sessions"))


def _session_file(store: FileSessionStore, session_id: str) -> Path:
    """Derive the on-disk path for a session (mirrors the store's naming logic)."""
    return store._path / hashlib.sha256(session_id.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Basic CRUD
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_read_write_roundtrip(store: FileSessionStore) -> None:
    sid = await store.write("sess-1", b"hello", lifetime=3600, ttl=3600)
    assert sid == "sess-1"
    assert await store.read("sess-1", lifetime=3600) == b"hello"


@pytest.mark.asyncio
async def test_read_missing_returns_empty(store: FileSessionStore) -> None:
    assert await store.read("nonexistent", lifetime=3600) == b""


@pytest.mark.asyncio
async def test_remove(store: FileSessionStore) -> None:
    await store.write("sess-del", b"data", lifetime=3600, ttl=3600)
    await store.remove("sess-del")
    assert await store.read("sess-del", lifetime=3600) == b""


@pytest.mark.asyncio
async def test_exists(store: FileSessionStore) -> None:
    assert not await store.exists("nope")
    await store.write("sess-ex", b"x", lifetime=3600, ttl=3600)
    assert await store.exists("sess-ex")


@pytest.mark.asyncio
async def test_remove_missing_is_noop(store: FileSessionStore) -> None:
    await store.remove("missing")  # should not raise


# ---------------------------------------------------------------------------
# TTL / lifetime expiry
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_read_expired_session_returns_empty(store: FileSessionStore) -> None:
    await store.write("sess-old", b"stale", lifetime=10, ttl=10)
    # Backdate the file mtime to simulate expiry
    file_path = _session_file(store, "sess-old")
    old_time = time.time() - 20
    os.utime(file_path, (old_time, old_time))

    assert await store.read("sess-old", lifetime=10) == b""
    assert not file_path.exists(), "Expired file should be removed on read"


@pytest.mark.asyncio
async def test_read_with_zero_lifetime_skips_expiry(store: FileSessionStore) -> None:
    await store.write("sess-zero", b"ok", lifetime=0, ttl=0)
    file_path = _session_file(store, "sess-zero")
    old_time = time.time() - 999999
    os.utime(file_path, (old_time, old_time))

    assert await store.read("sess-zero", lifetime=0) == b"ok"


# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cleanup_removes_expired_files(store: FileSessionStore) -> None:
    await store.write("fresh", b"a", lifetime=3600, ttl=3600)
    await store.write("stale1", b"b", lifetime=3600, ttl=3600)
    await store.write("stale2", b"c", lifetime=3600, ttl=3600)

    old_time = time.time() - 7200
    for sid in ("stale1", "stale2"):
        os.utime(_session_file(store, sid), (old_time, old_time))

    removed = await store.cleanup(lifetime=3600)
    assert removed == 2
    assert await store.exists("fresh")
    assert not await store.exists("stale1")
    assert not await store.exists("stale2")


@pytest.mark.asyncio
async def test_cleanup_with_zero_lifetime_removes_nothing(store: FileSessionStore) -> None:
    await store.write("a", b"x", lifetime=0, ttl=0)
    removed = await store.cleanup(lifetime=0)
    assert removed == 0


# ---------------------------------------------------------------------------
# Path-safety
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_path_traversal_is_contained_to_session_dir(store: FileSessionStore, tmp_path: Path) -> None:
    traversal_id = "../../outside/passwd"
    await store.write(traversal_id, b"evil", lifetime=3600, ttl=3600)

    # The derived file path must be inside the session directory
    file_path = _session_file(store, traversal_id)
    session_dir = store._path
    assert file_path.is_relative_to(session_dir), "Session file must be inside the session directory"

    # No files must have been created outside the session directory
    outside_files = [p for p in tmp_path.rglob("*") if p.is_file() and not p.is_relative_to(session_dir)]
    assert outside_files == [], f"Files written outside session dir: {outside_files}"

    # Data is still readable back via the same session ID
    assert await store.read(traversal_id, lifetime=3600) == b"evil"
