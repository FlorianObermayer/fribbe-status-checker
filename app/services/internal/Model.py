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
        self._device_names = [name.lower() for name in (device_names or [])]

    @classmethod
    def from_dict(cls, d: dict[str, str]) -> Self:
        warden = Wardens.by_name(d["name"])
        return cls(
            name=warden.name,
            device_macs=warden.device_macs,
            device_names=warden.device_names,
        )

    def to_dict(self) -> dict[str, str]:
        return {"name": self.name}


class Wardens:
    _team: list[Warden] = [
        Warden(
            "Flo",
            [
                "26:2d:12:cd:58:23",  # MacBook
                "aa:1a:9e:2e:aa:eb",  # Samsung Galaxy S24+
            ],
        ),
        Warden("Schnapsi", ["B2:38:95:80:29:D7", "74:60:FA:A2:94:E3"]),
        Warden("Kika", ["5a:5f:6e:2e:d3:ce"]),
        Warden("Jannik"),
    ]

    @staticmethod
    def first_or_none(device_mac: str | None, device_name: str | None) -> Warden | None:
        for warden in Wardens._team:
            if (device_mac and device_mac.lower() in warden.device_macs) or (
                device_name and device_name.lower() in warden.device_names
            ):
                return warden
        return None

    @staticmethod
    def by_name(name: str) -> Warden:
        for warden in Wardens._team:
            if warden.name.lower() == name.lower():
                return warden
        raise ValueError(f"No warden found with name {name}")
