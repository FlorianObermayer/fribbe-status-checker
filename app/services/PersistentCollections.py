import json
import os
import tempfile
import threading
from collections.abc import Iterator, MutableMapping
from contextlib import contextmanager, suppress
from datetime import datetime
from inspect import isclass
from pathlib import Path
from typing import (
    Any,
    Protocol,
    Self,
    TypeVar,
    get_args,
    get_origin,
    runtime_checkable,
)
from zoneinfo import ZoneInfo

from readerwriterlock import rwlock

V = TypeVar("V")


@runtime_checkable
class DictSerializable(Protocol):
    def to_dict(self) -> dict[str, str]: ...

    @classmethod
    def from_dict(cls, d: dict[str, str]) -> Self: ...


class ConversionHelper:
    @staticmethod
    def list_to_range(lst: list[int]):
        if len(lst) == 1:
            return range(lst[0], lst[0] + 1)

        step = lst[1] - lst[0]
        for i in range(2, len(lst)):
            if lst[i] - lst[i - 1] != step:
                raise ValueError("List is not evenly spaced, cannot convert to range")

        return range(lst[0], lst[-1] + step, step)


class PersistentDict[V](MutableMapping[str, V]):
    def __init__(self, path: str, value_type: type[V]):
        self._path = path
        self._value_type = value_type
        self._data: dict[str, V] = {}
        self._lock = rwlock.RWLockFair()
        self._batch_owner: int | None = None
        self._batch_depth = 0
        self._batch_wlock: rwlock.RWLockFair._aWriter | None = None  # pyright: ignore[reportPrivateUsage]

        if not self._is_type_supported(value_type):
            raise TypeError(
                f"PersistentDict: Type {value_type} is not supported. "
                "Must be a primitive type, range, datetime, DictSerializable, or a container "
                "of supported types."
            )

        self._load()

    def _is_type_supported(self, t: type[V]) -> bool:
        """Check if the type can be serialized/deserialized"""
        # Handle None/Any
        if t is type(None) or t is type[Any]:
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
        if origin in (list, list, dict, dict, tuple, tuple, set, set):
            args = get_args(t)
            if not args:  # Unparameterized container (e.g. just 'list')
                return True
            # Recursively check element types
            if origin in (list, list, tuple, tuple, set, set):
                return self._is_type_supported(args[0])
            elif origin in (dict, dict):
                return self._is_type_supported(args[0]) and self._is_type_supported(  # key type
                    args[1]
                )  # value type

        return False

    def _is_primitive(self, t: type[V] | type[Any]) -> bool:
        return t in (int, float, str, bool, type(None))

    def _is_primitive_type(self, t: type[V] | None = None) -> bool:
        t = t or self._value_type
        if self._is_primitive(t):
            return True

        origin = get_origin(t)
        if origin is None:
            return False

        if origin in (list, list, tuple, tuple, set, set, dict, dict):
            args = get_args(t)
            if not args:
                return True
            return all(self._is_primitive_type(arg) for arg in args)
        return False

    def _deserialize(self, value: Any, expected_type: type[V] | type[Any]) -> Any:
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

        if origin in (list, list):
            element_type = get_args(expected_type)[0] if get_args(expected_type) else type[Any]
            return [self._deserialize(item, element_type) for item in value]

        elif origin in (tuple, tuple):
            element_types = get_args(expected_type)
            if not element_types:
                return tuple(value)
            if len(element_types) == 2 and element_types[1] is ...:
                return tuple(self._deserialize(item, element_types[0]) for item in value)
            else:
                return tuple(self._deserialize(item, typ) for item, typ in zip(value, element_types, strict=False))

        elif origin in (set, set):
            element_type = get_args(expected_type)[0] if get_args(expected_type) else type[Any]
            return {self._deserialize(item, element_type) for item in value}

        elif origin in (dict, dict):
            key_type, val_type = get_args(expected_type) if get_args(expected_type) else (type[Any], type[Any])
            return {self._deserialize(k, key_type): self._deserialize(v, val_type) for k, v in value.items()}

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
        if Path(self._path).exists():
            with Path(self._path).open(encoding="utf-8") as f:
                raw_data = json.load(f)

            self._data = {k: self._deserialize(v, self._value_type) for k, v in raw_data.items()}
        else:
            self._data = {}

    def _save(self):
        parent = Path(self._path).parent
        parent.mkdir(parents=True, exist_ok=True)
        serialized = {k: self._serialize(v) for k, v in self._data.items()}
        fd, tmp_path = tempfile.mkstemp(dir=str(parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(serialized, f, ensure_ascii=False, indent=2)
            Path(tmp_path).replace(self._path)
        except BaseException:
            with suppress(OSError):
                Path(tmp_path).unlink()
            raise

    @property
    def _in_batch(self) -> bool:
        """True only when the *current* thread owns the batch write lock."""
        return self._batch_owner == threading.get_ident() and self._batch_depth > 0

    def __getitem__(self, key: str) -> V:
        if self._in_batch:
            return self._data[key]
        with self._lock.gen_rlock():
            return self._data[key]

    def __setitem__(self, key: str, value: V) -> None:
        if self._in_batch:
            self._data[key] = value
            return
        with self._lock.gen_wlock():
            self._data[key] = value
            self._save()

    def __delitem__(self, key: str) -> None:
        if self._in_batch:
            del self._data[key]
            return
        with self._lock.gen_wlock():
            del self._data[key]
            self._save()

    def __iter__(self):
        if self._in_batch:
            return iter(list(self._data))
        with self._lock.gen_rlock():
            return iter(list(self._data))

    def __len__(self) -> int:
        if self._in_batch:
            return len(self._data)
        with self._lock.gen_rlock():
            return len(self._data)

    def __contains__(self, key: object) -> bool:
        if self._in_batch:
            return key in self._data
        with self._lock.gen_rlock():
            return key in self._data

    def values(self):  # type: ignore[override]
        if self._in_batch:
            return list(self._data.values())
        with self._lock.gen_rlock():
            return list(self._data.values())

    def items(self):  # type: ignore[override]
        if self._in_batch:
            return list(self._data.items())
        with self._lock.gen_rlock():
            return list(self._data.items())

    def get(self, key: str, default: V | None = None) -> V | None:  # type: ignore[override]
        if self._in_batch:
            return self._data.get(key, default)
        with self._lock.gen_rlock():
            return self._data.get(key, default)

    def clear(self) -> None:
        if self._in_batch:
            self._data.clear()
            return
        with self._lock.gen_wlock():
            self._data.clear()
            self._save()

    def reload(self) -> None:
        """Reload the data from disk."""
        with self._lock.gen_wlock():
            self._load()

    @contextmanager
    def batch_write(self) -> Iterator["PersistentDict[V]"]:
        """Hold the write lock across multiple mutations, saving once when the block exits.

        Inside the block, direct dict-style access (``d[k] = v``, ``del d[k]``)
        skips per-operation locking and saving. A single ``_save()`` is always
        performed when the outermost batch block exits, regardless of whether
        the block raised an exception (i.e. in a ``finally`` clause).

        The "in batch" state is scoped to the owning thread so that other
        threads still acquire the RW lock normally.  Nested calls on the same
        thread only increment the depth counter — they do not attempt to
        re-acquire the write lock, which is not re-entrant.
        """
        is_outermost = threading.get_ident() != self._batch_owner
        if is_outermost:
            wlock = self._lock.gen_wlock()
            wlock.acquire()
            self._batch_wlock = wlock
            self._batch_owner = threading.get_ident()
        self._batch_depth += 1
        try:
            yield self
        finally:
            self._batch_depth -= 1
            if self._batch_depth == 0:
                self._batch_owner = None
                wlock = self._batch_wlock
                self._batch_wlock = None
                try:
                    self._save()
                finally:
                    if wlock is not None:
                        wlock.release()


class PersistentList[V]:
    def __init__(self, path: str, value_type: type[V]):
        self._dict: PersistentDict[list[V]] = PersistentDict(path, list[value_type])
        if self._dict.get("items") is None:
            self._dict["items"] = []

    def _get_items(self):
        return [*self._dict["items"]]

    def _set_items(self, new_items: list[V]):
        self._dict["items"] = new_items

    def append(self, value: V):
        items = self._get_items()
        items.append(value)
        self._set_items(items)

    def extend(self, values: list[V]):
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


class PersistentObject[V]:
    """A persistent storage for a single object of type V.

    Similar to PersistentList but only stores and manages a single value.
    The value is stored under a fixed key in a PersistentDict.
    """

    _VALUE_KEY = "value"

    def __init__(self, path: str, value_type: type[V], default_value: V | None = None):
        """Initialize a new PersistentObject.

        Args:
            path: The file path where the object should be stored
            value_type: The type of the value to store
            default_value: Optional default value if no value exists yet
        """
        self._dict: PersistentDict[V] = PersistentDict(path, value_type)
        if default_value is not None and self._dict.get(PersistentObject._VALUE_KEY) is None:
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


class PersistentDescriptor[V]:
    def __init__(self, name: str, field_type: type[V], default_value: V, storage_attr: str, lock: rwlock.RWLockFair):
        self._name = name
        self._field_type = field_type
        self._default_value = default_value
        self._lock = lock
        self._storage_attr = storage_attr

    def _get_storage(self, instance: Any) -> PersistentObject[V]:
        with self._lock.gen_rlock():
            if not isinstance(instance, PersistentPathProvider):
                raise TypeError(f"Class {instance.__class__.__name__} must implement PersistentPathProvider")

            # Create storage if it doesn't exist
            if not hasattr(instance, self._storage_attr):
                base_path = instance.get_path()
                file_path = str(Path(base_path) / f"{self._name}.json")
                setattr(
                    instance, self._storage_attr, PersistentObject(file_path, self._field_type, self._default_value)
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


def persistent[V](field_type: type[V], name: str, default_value: V) -> PersistentDescriptor[V]:
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
