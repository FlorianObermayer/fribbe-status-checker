from inspect import isclass
from typing import (
    List,
    Optional,
    Protocol,
    Self,
    Set,
    Tuple,
    TypeVar,
    Dict,
    Any,
    Type,
    MutableMapping,
    Generic,
    cast,
    get_args,
    get_origin,
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
        self._data: Dict[str, V] = {}

        if not self._is_type_supported(value_type):
            raise TypeError(
                f"PersistentDict: Type {value_type} is not supported. "
                "Must be a primitive type, DictSerializable, or a container "
                "of supported types."
            )

        self._load()

    def _is_type_supported(self, t: Type[V]) -> bool:
        """Check if the type can be serialized/deserialized"""
        # Handle None/Any
        if t is type(None) or t is Type[Any]:
            return True

        # Check for primitive types
        if self._is_primitive(t):
            return True

        # Check for DictSerializable types
        if isclass(t) and issubclass(t, DictSerializable):
            return True

        if hasattr(t, "from_dict") and hasattr(t, "to_dict"):
            return True

        # Handle generic containers
        origin = get_origin(t)
        if origin is None:
            return False

        # Check container types (list, dict, etc.)
        if origin in (list, List, dict, Dict, tuple, Tuple, set, Set):
            args = get_args(t)
            if not args:  # Unparameterized container (e.g. just 'list')
                return True
            # Recursively check element types
            if origin in (list, List, tuple, Tuple, set, Set):
                return self._is_type_supported(args[0])
            elif origin in (dict, Dict):
                return self._is_type_supported(
                    args[0]
                ) and self._is_type_supported(  # key type
                    args[1]
                )  # value type

        return False

    def _is_primitive(self, t: Type[V] | Type[Any]) -> bool:
        return t in (int, float, str, bool, type(None))

    def _is_primitive_type(self, t: Optional[Type[V]] = None) -> bool:
        t = t or self._value_type
        if self._is_primitive(t):
            return True

        origin = get_origin(t)
        if origin is None:
            return False

        if origin in (list, List, tuple, Tuple, set, Set, dict, Dict):
            args = get_args(t)
            if not args:
                return True
            return all(self._is_primitive_type(arg) for arg in args)
        return False

    def _deserialize(self, value: Any, expected_type: Type[V] | Type[Any]) -> Any:
        if value is None:
            return None

        if self._is_primitive(expected_type):
            if expected_type is int:
                return int(value)
            if expected_type is float:
                return float(value)
            if expected_type is bool:
                return bool(value)
            if expected_type is str:
                return str(value)
            return value

        origin = get_origin(expected_type) or expected_type

        if isinstance(origin, type) and issubclass(origin, DictSerializable):
            return origin.from_dict(value)

        if origin in (list, List):
            element_type = (
                get_args(expected_type)[0] if get_args(expected_type) else Type[Any]
            )
            return [self._deserialize(item, element_type) for item in value]

        elif origin in (tuple, Tuple):
            element_types = get_args(expected_type)
            if not element_types:
                return tuple(value)
            if len(element_types) == 2 and element_types[1] is ...:
                return tuple(
                    self._deserialize(item, element_types[0]) for item in value
                )
            else:
                return tuple(
                    self._deserialize(item, typ)
                    for item, typ in zip(value, element_types)
                )

        elif origin in (set, Set):
            element_type = (
                get_args(expected_type)[0] if get_args(expected_type) else Type[Any]
            )
            return {self._deserialize(item, element_type) for item in value}

        elif origin in (dict, Dict):
            key_type, val_type = (
                get_args(expected_type)
                if get_args(expected_type)
                else (Type[Any], Type[Any])
            )
            return {
                self._deserialize(k, key_type): self._deserialize(v, val_type)
                for k, v in value.items()
            }

        return value

    def _serialize(self, value: Any) -> Any:
        if value is None:
            return None

        if isinstance(value, (int, float, str, bool)):
            return value

        if isinstance(value, DictSerializable):
            return value.to_dict()

        if isinstance(value, (list, tuple, set)):
            return [self._serialize(item) for item in value]

        if isinstance(value, dict):
            return {str(k): self._serialize(v) for k, v in value.items()}

        return str(value)

    def _load(self):
        if os.path.exists(self._path):
            with open(self._path, "r", encoding="utf-8") as f:
                raw_data = json.load(f)

            self._data = {
                k: self._deserialize(v, self._value_type) for k, v in raw_data.items()
            }
        else:
            self._data = {}

    def _save(self):
        with open(self._path, "w", encoding="utf-8") as f:
            serialized = {k: self._serialize(v) for k, v in self._data.items()}
            json.dump(
                serialized,
                f,
                ensure_ascii=False,
                indent=2,
            )

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


class PersistentList(Generic[V]):

    def __init__(self, path: str, value_type: Type[V]):
        self._dict: PersistentDict[List[V]] = PersistentDict(path, List[value_type])
        if self._dict.get("items") is None:
            self._dict["items"] = []

    def _get_items(self):
        return [*self._dict["items"]]

    def _set_items(self, new_items: List[V]):
        self._dict["items"] = new_items

    def append(self, value: V):
        items = self._get_items()
        items.append(value)
        self._set_items(items)

    def extend(self, values: List[V]):
        items = self._get_items()
        items.extend(values)
        self._set_items(items)

    def __getitem__(self, idx: int):
        items = self._get_items()
        return items[idx]

    def __setitem__(self, idx: int, value: V):
        items = self._get_items()
        items[idx] = value
        self._set_items(items)

    def __delitem__(self, idx: int):
        items = self._get_items()
        del items[idx]
        self._dict["items"] = items

    def __len__(self):
        return len(self._get_items())

    def __iter__(self):
        return iter(self._get_items())

    def clear(self):
        self._set_items([])

    def to_list(self):
        return self._get_items()
