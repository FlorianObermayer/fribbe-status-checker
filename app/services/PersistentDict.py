from typing import (
    Optional,
    Protocol,
    Self,
    TypeVar,
    Dict,
    Any,
    Type,
    MutableMapping,
    Generic,
    runtime_checkable,
)

import json
import os

K = TypeVar("K", bound=str)
V = TypeVar("V")


@runtime_checkable
class DictSerializable(Protocol):
    def to_dict(self) -> Dict[str, Any]: ...
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> Self: ...


PRIMITIVE_TYPES = (int, float, str, bool, dict, list)


class PersistentDict(MutableMapping[K, V], Generic[K, V]):
    def __init__(self, path: str, value_type: Optional[Type[V]] = None):
        self._path = path
        self._value_type = value_type
        if self._value_type not in PRIMITIVE_TYPES and not self._is_dict_serializable():
            raise TypeError(
                "PersistentDict: value_type must be a primitive type or implement to_dict/from_dict!"
            )
        self._load()

    def _is_dict_serializable(self) -> bool:
        return (
            self._value_type is not None
            and hasattr(self._value_type, "from_dict")
            and hasattr(self._value_type, "to_dict")
        )

    def _load(self):
        if os.path.exists(self._path):
            with open(self._path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            if self._value_type in PRIMITIVE_TYPES:
                self._data = {k: v for k, v in raw.items()}
            elif self._is_dict_serializable():
                self._data = {k: self._value_type.from_dict(v) for k, v in raw.items()}  # type: ignore
            else:
                self._data = {k: self._value_type(v) for k, v in raw.items()}  # type: ignore
        else:
            self._data = {}

    def _save(self):
        with open(self._path, "w", encoding="utf-8") as f:
            if self._value_type in PRIMITIVE_TYPES:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
            elif self._is_dict_serializable():
                serializable = {k: v.to_dict() for k, v in self._data.items()}  # type: ignore
                json.dump(serializable, f, ensure_ascii=False, indent=2)
            else:
                serializable = {k: v for k, v in self._data.items()}
                json.dump(serializable, f, ensure_ascii=False, indent=2)

    def __getitem__(self, key: K) -> V:
        return self._data[key]

    def __setitem__(self, key: K, value: V) -> None:
        self._data[key] = value
        self._save()

    def __delitem__(self, key: K) -> None:
        del self._data[key]
        self._save()

    def __iter__(self):
        return iter(self._data)

    def __len__(self) -> int:
        return len(self._data)
