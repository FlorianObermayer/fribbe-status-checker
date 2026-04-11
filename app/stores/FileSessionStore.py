"""File-based session store for starsessions.

Stores serialised session data as individual files on disk.  The file name
is derived from the session ID after stripping any path-traversal characters.
"""

from pathlib import Path

from starsessions import SessionStore


class FileSessionStore(SessionStore):
    def __init__(self, path: str) -> None:
        self._path = Path(path)
        self._path.mkdir(parents=True, exist_ok=True)

    def _file_path(self, session_id: str) -> Path:
        safe_id = "".join(c for c in session_id if c.isalnum() or c in "-_")
        return self._path / safe_id

    async def read(self, session_id: str, lifetime: int) -> bytes:
        try:
            return self._file_path(session_id).read_bytes()
        except FileNotFoundError:
            return b""

    async def write(self, session_id: str, data: bytes, lifetime: int, ttl: int) -> str:
        self._file_path(session_id).write_bytes(data)
        return session_id

    async def remove(self, session_id: str) -> None:
        self._file_path(session_id).unlink(missing_ok=True)

    async def exists(self, session_id: str) -> bool:
        return self._file_path(session_id).exists()
