from typing import (
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

V = TypeVar("V")

@runtime_checkable
class DictSerializable(Protocol):
    def to_dict(self) -> Dict[str, Any]: ...
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> Self: ...


class PersistentDict(MutableMapping[str, V], Generic[V]):
    def __init__(self, path: str, value_type: Type[V]):
        self._path = path
        self._value_type = value_type
        if not self._is_primitive_type() and not self._is_dict_serializable():
            raise TypeError(
                "PersistentDict: value_type must be a primitive type or implement to_dict/from_dict!"
            )
        self._data: Dict[str, V] = {}
        self._load()

    def _is_primitive_type(self) -> bool:
        primitive_types = (int, float, str, bool, dict, list)
        # Handle generics like dict[str, int], list[int], etc.
        origin = getattr(self._value_type, "__origin__", None)
        if origin in (dict, list):
            return True
        return self._value_type in primitive_types

    def _is_dict_serializable(self) -> bool:
        return hasattr(self._value_type, "from_dict") and hasattr(
            self._value_type, "to_dict"
        )

    def _load(self):
        if os.path.exists(self._path):
            with open(self._path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            if self._is_primitive_type():
                self._data = {k: v for k, v in raw.items()}
            elif self._is_dict_serializable():
                self._data = {k: self._value_type.from_dict(v) for k, v in raw.items()}  # type: ignore
            else:
                self._data = {k: self._value_type(v) for k, v in raw.items()}  # type: ignore
        else:
            self._data = {}

    def _save(self):
        with open(self._path, "w", encoding="utf-8") as f:
            if self._is_primitive_type():
                json.dump(self._data, f, ensure_ascii=False, indent=2)
            elif self._is_dict_serializable():
                serializable = {k: v.to_dict() for k, v in self._data.items()}  # type: ignore
                json.dump(serializable, f, ensure_ascii=False, indent=2)
            else:
                serializable = {k: v for k, v in self._data.items()}
                json.dump(serializable, f, ensure_ascii=False, indent=2)

    def __getitem__(self, key: str) -> V:
        return self._data[key]

    def __setitem__(self, key: str, value: V) -> None:
        self._data[key] = value
        self._save()

    def __delitem__(self, key: str) -> None:
        del self._data[key]
        self._save()

    def __iter__(self):
        return iter(self._data)

    def __len__(self) -> int:
        return len(self._data)
