from typing import List


class Warden:
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


class Wardens:
    _team: List[Warden] = [
        Warden(
            "Flo",
            [
                "26:2d:12:cd:58:23",  # MacBook
                "aa:1a:9e:2e:aa:eb",  # Samsung Galaxy S24+
            ],
        ),
        Warden("Schnapsi", device_names=["dodelido"]),
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
