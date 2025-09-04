from typing import Dict, List, Self

from app.services.PersistentCollections import DictSerializable


class Warden(DictSerializable):
    @property
    def name(self) -> str:
        return self._name

    @property
    def device_macs(self) -> List[str]:
        return self._device_macs

    @property
    def device_names(self) -> List[str]:
        return self._device_names

    def __init__(self, name: str, device_macs:List[str] = [], device_names: List[str] = []):
        self._name = name
        self._device_macs = [mac.lower() for mac in device_macs]
        self._device_names = [name.lower() for name in device_names]

    @classmethod
    def from_dict(cls, d: Dict[str, str]) -> Self:
        warden = Wardens.by_name(d["name"])
        return cls(
            name=warden.name,
            device_macs=warden.device_macs,
            device_names=warden.device_names,
        )

    def to_dict(self) -> Dict[str, str]:
        return {"name": self.name}


class Wardens:
    _team: List[Warden] = [
        Warden(
            "Flo",
            [
                "REDACTED_MAC",  # MacBook
                "REDACTED_MAC",  # Samsung Galaxy S24+
            ],
        ),
        Warden("REDACTED_NAME", [
            "REDACTED_MAC",
            "REDACTED_MAC"
            ]
        ),
        Warden("REDACTED_NAME", ["REDACTED_MAC"]),
        Warden("REDACTED_NAME"),
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
