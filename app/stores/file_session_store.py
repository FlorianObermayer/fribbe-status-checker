"""File-based session store for starsessions.

Stores serialised session data as individual files on disk.  The file name
is the SHA-256 hex digest of the session ID, which is stable, collision-free,
never empty, and contains only filesystem-safe characters.

IO is offloaded to a thread-pool so the ASGI event loop is never blocked.
Each session file's mtime is checked against the ``lifetime`` / ``ttl``
parameters to expire stale sessions, and a periodic cleanup task removes
orphaned files.
"""

import asyncio
import hashlib
import logging
import os
import tempfile
import time
from pathlib import Path

from starsessions import SessionStore

_logger = logging.getLogger(__name__)


class FileSessionStore(SessionStore):
    """File-based session store backed by individual files on disk."""

    def __init__(self, path: str) -> None:
        self._path = Path(path)
        self._path.mkdir(parents=True, exist_ok=True)

    def _file_path(self, session_id: str) -> Path:
        return self._path / hashlib.sha256(session_id.encode()).hexdigest()

    # -- sync helpers (run inside the thread-pool) --------------------------

    def _read_sync(self, file_path: Path, lifetime: int) -> bytes:
        try:
            mtime = file_path.stat().st_mtime
            if lifetime > 0 and (time.time() - mtime) > lifetime:
                file_path.unlink(missing_ok=True)
                return b""
            return file_path.read_bytes()
        except FileNotFoundError:
            return b""

    def _write_sync(self, file_path: Path, data: bytes) -> None:
        fd, tmp = tempfile.mkstemp(dir=file_path.parent)
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(data)
            Path(tmp).replace(file_path)
        except Exception:
            Path(tmp).unlink(missing_ok=True)
            raise

    def _remove_sync(self, file_path: Path) -> None:
        file_path.unlink(missing_ok=True)

    def _cleanup_sync(self, lifetime: int) -> int:
        """Remove session files older than *lifetime* seconds.  Returns count of removed files."""
        if lifetime <= 0:
            return 0
        now = time.time()
        removed = 0
        for entry in os.scandir(self._path):
            if entry.is_file() and (now - entry.stat().st_mtime) > lifetime:
                Path(entry.path).unlink(missing_ok=True)
                removed += 1
        return removed

    # -- async interface (SessionStore) -------------------------------------

    async def read(self, session_id: str, lifetime: int) -> bytes:
        """Read session data, returning empty bytes if missing or expired."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._read_sync, self._file_path(session_id), lifetime)

    async def write(self, session_id: str, data: bytes, lifetime: int, ttl: int) -> str:  # noqa: ARG002
        """Write session data and return the session ID."""
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._write_sync, self._file_path(session_id), data)
        return session_id

    async def remove(self, session_id: str) -> None:
        """Remove a session file from disk."""
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._remove_sync, self._file_path(session_id))

    async def exists(self, session_id: str) -> bool:
        """Check whether a session file exists on disk."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._file_path(session_id).exists)

    async def cleanup(self, lifetime: int) -> int:
        """Remove all session files older than *lifetime* seconds."""
        loop = asyncio.get_running_loop()
        removed: int = await loop.run_in_executor(None, self._cleanup_sync, lifetime)
        if removed:
            _logger.info("Session cleanup: removed %d expired session file(s)", removed)
        return removed
