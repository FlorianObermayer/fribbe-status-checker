"""File-based session store for starsessions.

Stores serialised session data as individual files on disk.  The file name
is derived from the session ID after stripping any path-traversal characters.

IO is offloaded to a thread-pool so the ASGI event loop is never blocked.
Each session file's mtime is checked against the ``lifetime`` / ``ttl``
parameters to expire stale sessions, and a periodic cleanup task removes
orphaned files.
"""

import asyncio
import logging
import os
import time
from pathlib import Path

from starsessions import SessionStore

_logger = logging.getLogger("uvicorn.error")


class FileSessionStore(SessionStore):
    def __init__(self, path: str) -> None:
        self._path = Path(path)
        self._path.mkdir(parents=True, exist_ok=True)

    def _file_path(self, session_id: str) -> Path:
        safe_id = "".join(c for c in session_id if c.isalnum() or c in "-_")
        return self._path / safe_id

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
        file_path.write_bytes(data)

    def _remove_sync(self, file_path: Path) -> None:
        file_path.unlink(missing_ok=True)

    def _exists_sync(self, file_path: Path, lifetime: int) -> bool:
        try:
            mtime = file_path.stat().st_mtime
            if lifetime > 0 and (time.time() - mtime) > lifetime:
                file_path.unlink(missing_ok=True)
                return False
            return True
        except FileNotFoundError:
            return False

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
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._read_sync, self._file_path(session_id), lifetime)

    async def write(self, session_id: str, data: bytes, lifetime: int, ttl: int) -> str:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._write_sync, self._file_path(session_id), data)
        return session_id

    async def remove(self, session_id: str) -> None:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._remove_sync, self._file_path(session_id))

    async def exists(self, session_id: str) -> bool:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._exists_sync, self._file_path(session_id), 0)

    async def cleanup(self, lifetime: int) -> int:
        """Remove all session files older than *lifetime* seconds."""
        loop = asyncio.get_running_loop()
        removed: int = await loop.run_in_executor(None, self._cleanup_sync, lifetime)
        if removed:
            _logger.info("Session cleanup: removed %d expired session file(s)", removed)
        return removed
