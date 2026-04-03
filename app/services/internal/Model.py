from typing import Self

from app.services.PersistentCollections import DictSerializable


class Warden(DictSerializable):
    @property
    def name(self) -> str:
        return self._name

    @property
    def device_macs(self) -> list[str]:
        return self._device_macs

    @property
    def device_names(self) -> list[str]:
        return self._device_names

    def __init__(self, name: str, device_macs: list[str] | None = None, device_names: list[str] | None = None):
        self._name = name
        self._device_macs = [mac.lower() for mac in (device_macs or [])]
        self._device_names = [n.lower() for n in (device_names or [])]

    @classmethod
    def from_dict(cls, d: dict[str, str]) -> Self:
        return cls(name=d["name"])

    def to_dict(self) -> dict[str, str]:
        return {"name": self.name}


class Wardens:
    @staticmethod
    def first_or_none(device_mac: str | None, device_name: str | None) -> "Warden | None":
        from app.services.internal.WardenStore import WardenStore

        return WardenStore.get_instance().first_or_none(device_mac, device_name)

    @staticmethod
    def by_name(name: str) -> "Warden":
        from app.services.internal.WardenStore import WardenStore

        return WardenStore.get_instance().by_name(name)
