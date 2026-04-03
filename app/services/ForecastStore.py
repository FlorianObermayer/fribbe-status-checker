import os
import threading
from datetime import date
from typing import ClassVar

from readerwriterlock import rwlock

from app.services.PersistentCollections import PersistentDict

MAX_TOKENS_PER_DATE = 500


class ForecastStore:
    _instance: ClassVar["ForecastStore | None"] = None
    _instance_lock: ClassVar[threading.Lock] = threading.Lock()

    def __init__(self, path: str):
        self._store: PersistentDict[list[str]] = PersistentDict(path, list[str])
        self._lock = rwlock.RWLockFair()

    @classmethod
    def get_instance(cls) -> "ForecastStore":
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    path = os.path.join(os.environ["LOCAL_DATA_PATH"], "forecasts.json")
                    cls._instance = cls(path)
        return cls._instance

    def add(self, for_date: date, token: str) -> None:
        key = for_date.isoformat()
        with self._lock.gen_wlock():
            tokens = self._store.get(key) or []
            if token not in tokens:
                if len(tokens) >= MAX_TOKENS_PER_DATE:
                    return
                self._store[key] = [*tokens, token]

    def remove(self, for_date: date, token: str) -> None:
        key = for_date.isoformat()
        with self._lock.gen_wlock():
            tokens = self._store.get(key) or []
            if token in tokens:
                self._store[key] = [t for t in tokens if t != token]

    def count(self, for_date: date) -> int:
        with self._lock.gen_rlock():
            return len(self._store.get(for_date.isoformat()) or [])

    def has(self, for_date: date, token: str) -> bool:
        with self._lock.gen_rlock():
            return token in (self._store.get(for_date.isoformat()) or [])
