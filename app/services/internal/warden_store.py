import json
import os
import tempfile
import threading
from contextlib import suppress
from pathlib import Path
from typing import ClassVar

from readerwriterlock import rwlock

from app.config import cfg
from app.services.internal.model import Warden


class WardenStore:
    """Thread-safe JSON-backed store for warden records."""

    _instance: ClassVar["WardenStore | None"] = None
    _instance_lock: ClassVar[threading.Lock] = threading.Lock()

    def __init__(self, path: str) -> None:
        self._path = path
        self._lock = rwlock.RWLockFair()
        self._wardens: list[Warden] = []
        self._load()

    @classmethod
    def get_instance(cls) -> "WardenStore":
        """Return the singleton WardenStore instance."""
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    path = str(Path(cfg.LOCAL_DATA_PATH) / "internal" / "wardens.json")
                    cls._instance = cls(path)
        return cls._instance

    def _warden_to_raw(self, w: Warden) -> dict[str, str | list[str]]:
        return {"name": w.name, "device_macs": w.device_macs, "device_names": w.device_names}

    def _load(self) -> None:
        if Path(self._path).exists():
            with Path(self._path).open(encoding="utf-8") as f:
                data: dict[str, list[dict[str, str | list[str]]]] = json.load(f)
            self._wardens = [
                Warden(
                    str(w["name"]),
                    [str(m) for m in w.get("device_macs", [])],  # type: ignore[union-attr]
                    [str(n) for n in w.get("device_names", [])],  # type: ignore[union-attr]
                )
                for w in data.get("wardens", [])
            ]

    def _save(self) -> None:
        parent = Path(self._path).parent
        parent.mkdir(parents=True, exist_ok=True)
        data = {"wardens": [self._warden_to_raw(w) for w in self._wardens]}
        fd, tmp_path = tempfile.mkstemp(dir=str(parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            Path(tmp_path).replace(self._path)
        except BaseException:
            with suppress(OSError):
                Path(tmp_path).unlink()
            raise

    def get_all(self) -> list[Warden]:
        """Return a snapshot of all wardens."""
        with self._lock.gen_rlock():
            return [*self._wardens]

    def by_name(self, name: str) -> Warden:
        """Return the warden with the given name or raise ValueError."""
        with self._lock.gen_rlock():
            for warden in self._wardens:
                if warden.name.lower() == name.lower():
                    return warden
        msg = f"No warden found with name '{name}'"
        raise ValueError(msg)

    def first_or_none(self, device_mac: str | None, device_name: str | None) -> Warden | None:
        """Return the first warden matching a MAC or device name, or None."""
        with self._lock.gen_rlock():
            for warden in self._wardens:
                if (device_mac and device_mac.lower() in warden.device_macs) or (
                    device_name and device_name.lower() in warden.device_names
                ):
                    return warden
        return None

    def add(self, warden: Warden) -> None:
        """Add a new warden or raise ValueError if the name exists."""
        with self._lock.gen_wlock():
            for w in self._wardens:
                if w.name.lower() == warden.name.lower():
                    msg = f"Warden with name '{warden.name}' already exists"
                    raise ValueError(msg)
            self._wardens.append(warden)
            self._save()

    def update(self, name: str, updated: Warden) -> Warden:
        """Replace an existing warden by name or raise ValueError."""
        with self._lock.gen_wlock():
            for i, w in enumerate(self._wardens):
                if w.name.lower() == name.lower():
                    self._wardens[i] = updated
                    self._save()
                    return updated
        msg = f"No warden found with name '{name}'"
        raise ValueError(msg)

    def delete(self, name: str) -> None:
        """Delete a warden by name or raise ValueError."""
        with self._lock.gen_wlock():
            original_len = len(self._wardens)
            self._wardens = [w for w in self._wardens if w.name.lower() != name.lower()]
            if len(self._wardens) == original_len:
                msg = f"No warden found with name '{name}'"
                raise ValueError(msg)
            self._save()
