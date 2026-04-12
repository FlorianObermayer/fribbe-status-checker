from typing import Self

from app.services.persistent_collections import DictSerializable


class Warden(DictSerializable):
    """A named person whose devices are tracked for on-site detection."""

    @property
    def name(self) -> str:
        """Return the warden's display name."""
        return self._name

    @property
    def device_macs(self) -> list[str]:
        """Return the warden's registered MAC addresses."""
        return self._device_macs

    @property
    def device_names(self) -> list[str]:
        """Return the warden's registered device names."""
        return self._device_names

    def __init__(self, name: str, device_macs: list[str] | None = None, device_names: list[str] | None = None) -> None:
        self._name = name
        self._device_macs = [mac.lower() for mac in (device_macs or [])]
        self._device_names = [n.lower() for n in (device_names or [])]

    @classmethod
    def from_dict(cls, d: dict[str, str]) -> Self:
        """Deserialize from a plain dict."""
        return cls(name=d["name"])

    def to_dict(self) -> dict[str, str]:
        """Serialize to a plain dict."""
        return {"name": self.name}
