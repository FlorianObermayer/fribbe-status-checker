from pathlib import Path

from app import env
from app.services.persistent_collections import PersistentPathProvider, persistent
from app.services.presence_level import PresenceLevel


class PresenceThresholds(PersistentPathProvider):
    """Persisted device-count thresholds that determine PresenceLevel."""

    def __init__(self) -> None:
        self._min_non_empty_storage = persistent(int, "min_non_empty_ct", 2)
        self._min_many_storage = persistent(int, "min_many_ct", 10)

    def get_path(self) -> str:
        """Return the base path for threshold persistence."""
        return str(Path(env.LOCAL_DATA_PATH) / "presence_thresholds")

    @property
    def min_non_empty_ct(self) -> int:
        """Return the minimum device count to be considered non-empty."""
        return self._min_non_empty_storage.__get__(self, type(self))

    @min_non_empty_ct.setter
    def min_non_empty_ct(self, value: int) -> None:
        self._min_non_empty_storage.__set__(self, value)

    @property
    def min_many_ct(self) -> int:
        """Return the minimum device count to be considered 'many'."""
        return self._min_many_storage.__get__(self, type(self))

    @min_many_ct.setter
    def min_many_ct(self, value: int) -> None:
        self._min_many_storage.__set__(self, value)

    def get_thresholds(self) -> dict[PresenceLevel, int]:
        """Return the threshold mapping for each presence level."""
        return {
            PresenceLevel.EMPTY: self.min_non_empty_ct - 1,
            PresenceLevel.FEW: self.min_non_empty_ct,
            PresenceLevel.MANY: self.min_many_ct,
        }

    def get_presence_level(self, devices_ct: int) -> PresenceLevel:
        """Map a device count to the corresponding presence level."""
        match devices_ct:
            case ct if ct < self.min_non_empty_ct:
                return PresenceLevel.EMPTY
            case ct if ct >= self.min_non_empty_ct and ct < self.min_many_ct:
                return PresenceLevel.FEW
            case _:
                return PresenceLevel.MANY
