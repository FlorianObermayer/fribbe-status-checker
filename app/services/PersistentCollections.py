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
    get_args,
    get_origin,
    runtime_checkable,
)

import json
import os
from datetime import datetime
from zoneinfo import ZoneInfo
from readerwriterlock import rwlock

V = TypeVar("V")


@runtime_checkable
class DictSerializable(Protocol):

    def to_dict(self) -> Dict[str, str]: ...

    @classmethod
    def from_dict(cls, d: Dict[str, str]) -> Self: ...


class ConversionHelper():
        @staticmethod
        def list_to_range(lst: List[int]):
            if len(lst) == 1:
                return range(lst[0], lst[0] + 1)
            
            step = lst[1] - lst[0]
            for i in range(2, len(lst)):
                if lst[i] - lst[i-1] != step:
                    raise ValueError("List is not evenly spaced, cannot convert to range")
            
            return range(lst[0], lst[-1] + step, step)


class PersistentDict(MutableMapping[str, V], Generic[V]):
    def __init__(self, path: str, value_type: Type[V]):
        self._path = path
        self._value_type = value_type
        self._data: Dict[str, V] = {}

        if not self._is_type_supported(value_type):
            raise TypeError(
                f"PersistentDict: Type {value_type} is not supported. "
                "Must be a primitive type, range, datetime, DictSerializable, or a container "
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

        if t is range:
            return True
        
        if t is datetime:
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

        if expected_type is datetime:
            if isinstance(value, str):
                try:
                    # Try parsing with timezone info
                    return datetime.fromisoformat(value)
                except ValueError:
                    # If no timezone info, assume Europe/Berlin
                    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
                    return dt.astimezone(ZoneInfo("Europe/Berlin"))
            return value

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


        if expected_type is range:
            return ConversionHelper.list_to_range(value)
        
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

        if isinstance(value, datetime):
            return value.isoformat()

        if isinstance(value, (int, float, str, bool)):
            return value

        if isinstance(value, DictSerializable):
            return value.to_dict()

        if isinstance(value, (list, tuple, set)):
            return [self._serialize(item) for item in value]  # type: ignore

        if isinstance(value, dict):
            return {str(k): self._serialize(v) for k, v in value.items()}  # type: ignore

        if isinstance(value, range):
            return list(value)
        
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
        os.makedirs(os.path.dirname(self._path), exist_ok=True)
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

    def reload(self) -> None:
        """Reload the data from disk."""
        self._load()


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


class PersistentObject(Generic[V]):
    """A persistent storage for a single object of type V.

    Similar to PersistentList but only stores and manages a single value.
    The value is stored under a fixed key in a PersistentDict.
    """

    _VALUE_KEY = "value"

    def __init__(self, path: str, value_type: Type[V], default_value: V | None = None):
        """Initialize a new PersistentObject.

        Args:
            path: The file path where the object should be stored
            value_type: The type of the value to store
            default_value: Optional default value if no value exists yet
        """
        self._dict: PersistentDict[V] = PersistentDict(path, value_type)
        if (
            default_value is not None
            and self._dict.get(PersistentObject._VALUE_KEY) is None
        ):
            self._dict[PersistentObject._VALUE_KEY] = default_value

    def get(self) -> V | None:
        """Get the stored value or None if no value is stored."""
        # Reload the dictionary to get the latest value
        self._dict.reload()
        return self._dict.get(PersistentObject._VALUE_KEY)

    def set(self, value: V | None) -> None:
        """Set a new value or None to clear the stored value."""
        if value is None:
            if PersistentObject._VALUE_KEY in self._dict:
                del self._dict[PersistentObject._VALUE_KEY]
        else:
            self._dict[PersistentObject._VALUE_KEY] = value

    def clear(self) -> None:
        """Clear the stored value."""
        self.set(None)


@runtime_checkable
class PersistentPathProvider(Protocol):
    """Protocol for classes that can provide a path for persistence.
    
    Classes using @persistent properties must implement this protocol.
    """
    def get_path(self) -> str:
        """Get the base path where persistent properties should be stored.
        
        Returns:
            The absolute path to the directory where persistent files should be stored.
            Individual properties will be stored as separate files in this directory.
        """
        ...


class PersistentDescriptor(Generic[V]):
    def __init__(self, name: str, field_type: Type[V], default_value: V, storage_attr: str, lock: rwlock.RWLockFair):
        self._name = name
        self._field_type = field_type
        self._default_value = default_value
        self._lock = lock
        self._storage_attr = storage_attr

    def _get_storage(self, instance: Any) -> PersistentObject[V]:
        with self._lock.gen_rlock():
            if not isinstance(instance, PersistentPathProvider):
                raise TypeError(
                    f"Class {instance.__class__.__name__} must implement PersistentPathProvider"
                )

            # Create storage if it doesn't exist
            if not hasattr(instance, self._storage_attr):
                base_path = instance.get_path()
                file_path = os.path.join(base_path, f"{self._name}.json")
                setattr(
                    instance,
                    self._storage_attr,
                    PersistentObject(file_path,  self._field_type,  self._default_value)
                )

            return getattr(instance, self._storage_attr)

    def __get__(self, instance: Any, owner: Any) -> V:
        with self._lock.gen_rlock():
            if instance is None:
                return self._default_value
            storage = self._get_storage(instance)
            value = storage.get()
            return value if value is not None else self._default_value

    def __set__(self, instance: Any, value: V) -> None:
        with self._lock.gen_rlock():
            if instance is not None:
                storage = self._get_storage(instance)
                storage.set(value)

def persistent(field_type: Type[V], name: str, default_value: V) -> PersistentDescriptor[V]:
    """Create a persistent field descriptor.
    
    Creates a descriptor that automatically persists the field value to disk.
    The class must implement PersistentPathProvider to specify where to store the data.
    Can be used with dataclass fields or as a property decorator.
    
    Args:
        field_type: The type of the field (must be supported by PersistentDict)
        name: Name of the field
        default_value: Default value for the field
        
    Example:
        @dataclass
        class MyConfig(PersistentPathProvider):
            def get_path(self) -> str:
                return "/path/to/config/dir"
                
            # Use as field descriptor
            name: str = persistent(str, "name", "")
            count: int = persistent(int, "count", 0)
            
            # Or use as property decorator
            @persistent(int, "value", 0)
            @property
            def value(self) -> int:
                return self._value
    """
    _rwlock = rwlock.RWLockFair()
    storage_attr = f"_persistent_{name}_storage"
    return PersistentDescriptor(name, field_type, default_value, storage_attr, _rwlock)