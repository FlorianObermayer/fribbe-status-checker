import json
import os
import tempfile
import threading
from collections.abc import Callable, Generator, Iterator, MutableMapping
from contextlib import contextmanager, suppress
from datetime import datetime
from inspect import isclass
from pathlib import Path
from typing import (
    Any,
    ClassVar,
    Protocol,
    Self,
    TypeVar,
    get_args,
    get_origin,
    runtime_checkable,
)

from readerwriterlock import rwlock

V = TypeVar("V")


@runtime_checkable
class DictSerializable(Protocol):
    """Protocol for objects serializable to/from plain dicts."""

    def to_dict(self) -> dict[str, str]:
        """Serialize to a plain dict."""
        ...

    @classmethod
    def from_dict(cls, d: dict[str, str]) -> Self:
        """Deserialize from a plain dict."""
        ...


class ConversionHelper:
    """Utilities for converting between collection types."""

    @staticmethod
    def list_to_range(lst: list[int]) -> range:
        """Convert an evenly-spaced list of ints to a range."""
        if len(lst) == 1:
            return range(lst[0], lst[0] + 1)

        step = lst[1] - lst[0]
        for i in range(2, len(lst)):
            if lst[i] - lst[i - 1] != step:
                msg = "List is not evenly spaced, cannot convert to range"
                raise ValueError(msg)

        return range(lst[0], lst[-1] + step, step)


class PersistentDict[V](MutableMapping[str, V]):
    """Thread-safe JSON-backed dictionary with automatic persistence."""

    def __init__(self, path: str, value_type: type[V]) -> None:
        self._path = path
        self._value_type = value_type
        self._data: dict[str, V] = {}
        self._lock = rwlock.RWLockFair()
        self._batch_owner: int | None = None
        self._batch_depth = 0
        self._batch_wlock: rwlock.RWLockFair._aWriter | None = None  # pyright: ignore[reportPrivateUsage]

        if not self._is_type_supported(value_type):
            msg = (
                f"PersistentDict: Type {value_type} is not supported. "
                "Must be a primitive type, range, datetime, DictSerializable, or a container "
                "of supported types."
            )
            raise TypeError(
                msg,
            )

        self._load()

    _SCALAR_TYPES: ClassVar[set[type[object]]] = {type(None), int, float, str, bool, range, datetime}
    _CONTAINER_ORIGINS: ClassVar[set[type[object]]] = {list, dict, tuple, set}
    _SEQUENCE_ORIGINS: ClassVar[set[type[object]]] = {list, tuple, set}

    def _is_type_supported(self, t: type[V]) -> bool:
        """Check if the type can be serialized/deserialized."""
        if t in self._SCALAR_TYPES or t is type[Any]:
            return True
        if isclass(t) and issubclass(t, DictSerializable):
            return True
        if hasattr(t, "from_dict") and hasattr(t, "to_dict"):
            return True
        return self._is_container_type_supported(t)

    def _is_container_type_supported(self, t: type[V]) -> bool:
        origin = get_origin(t)
        if origin is None or origin not in self._CONTAINER_ORIGINS:
            return False
        args = get_args(t)
        if not args:
            return True
        if origin in self._SEQUENCE_ORIGINS:
            return self._is_type_supported(args[0])
        # dict: check key and value types
        return self._is_type_supported(args[0]) and self._is_type_supported(args[1])

    def _is_primitive(self, t: type[V] | type[Any]) -> bool:
        return t in (int, float, str, bool, type(None))

    def _is_primitive_type(self, t: type[V] | None = None) -> bool:
        t = t or self._value_type
        if self._is_primitive(t):
            return True

        origin = get_origin(t)
        if origin is None:
            return False

        if origin in self._CONTAINER_ORIGINS:
            args = get_args(t)
            if not args:
                return True
            return all(self._is_primitive_type(arg) for arg in args)
        return False

    def _deserialize(self, value: Any, expected_type: type[V] | type[Any]) -> Any:
        if value is None:
            return None
        if expected_type is datetime:
            return self._deserialize_datetime(value)
        if self._is_primitive(expected_type):
            return self._deserialize_primitive(value, expected_type)
        if expected_type is range:
            return ConversionHelper.list_to_range(value)
        return self._deserialize_complex(value, expected_type)

    def _deserialize_datetime(self, value: Any) -> Any:
        if isinstance(value, str):
            return datetime.fromisoformat(value)
        return value

    _PRIMITIVE_COERCIONS: ClassVar[dict[type[object], Callable[[Any], object]]] = {
        int: int,
        float: float,
        bool: bool,
        str: str,
    }

    def _deserialize_primitive(self, value: Any, expected_type: type[V] | type[Any]) -> Any:
        coerce = self._PRIMITIVE_COERCIONS.get(expected_type)  # pyright: ignore[reportArgumentType]
        return coerce(value) if coerce else value

    def _deserialize_complex(self, value: Any, expected_type: type[V] | type[Any]) -> Any:
        origin = get_origin(expected_type) or expected_type
        if isinstance(origin, type) and issubclass(origin, DictSerializable):
            return origin.from_dict(value)
        args = get_args(expected_type)
        if origin in (list, list):
            element_type = args[0] if args else type[Any]
            return [self._deserialize(item, element_type) for item in value]
        if origin in (tuple, tuple):
            return self._deserialize_tuple(value, args)
        if origin in (set, set):
            element_type = args[0] if args else type[Any]
            return {self._deserialize(item, element_type) for item in value}  # pyright: ignore[reportUnknownVariableType]
        if origin in (dict, dict):
            key_type: type[Any] = args[0] if args else type[Any]
            val_type: type[Any] = args[1] if len(args) > 1 else type[Any]
            return {
                self._deserialize(k, key_type): self._deserialize(v, val_type)  # pyright: ignore[reportUnknownVariableType,reportUnknownArgumentType]
                for k, v in value.items()
            }
        return value

    _HOMOGENEOUS_TUPLE_ARGS = 2

    def _deserialize_tuple(self, value: Any, element_types: tuple[type[Any], ...]) -> tuple[Any, ...]:
        if not element_types:
            return tuple(value)
        if len(element_types) == self._HOMOGENEOUS_TUPLE_ARGS and element_types[1] is Ellipsis:  # pyright: ignore[reportUnnecessaryComparison]
            return tuple(self._deserialize(item, element_types[0]) for item in value)
        return tuple(self._deserialize(item, typ) for item, typ in zip(value, element_types, strict=False))

    def _serialize(self, value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, (int, float, str, bool)):
            return value
        return self._serialize_complex(value)

    def _serialize_complex(self, value: Any) -> Any:
        if isinstance(value, DictSerializable):
            return value.to_dict()
        if isinstance(value, (list, tuple, set)):
            return [self._serialize(item) for item in value]  # pyright: ignore[reportUnknownVariableType]
        if isinstance(value, dict):
            return {str(k): self._serialize(v) for k, v in value.items()}  # pyright: ignore[reportUnknownVariableType,reportUnknownArgumentType]
        if isinstance(value, range):
            return list(value)
        return str(value)

    def _load(self) -> None:
        if Path(self._path).exists():
            with Path(self._path).open(encoding="utf-8") as f:
                raw_data = json.load(f)

            self._data = {k: self._deserialize(v, self._value_type) for k, v in raw_data.items()}
        else:
            self._data = {}

    def _save(self) -> None:
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
        """Return the value for key."""
        if self._in_batch:
            return self._data[key]
        with self._lock.gen_rlock():
            return self._data[key]

    def __setitem__(self, key: str, value: V) -> None:
        """Set the value for key and persist."""
        if self._in_batch:
            self._data[key] = value
            return
        with self._lock.gen_wlock():
            self._data[key] = value
            self._save()

    def __delitem__(self, key: str) -> None:
        """Delete the entry for key and persist."""
        if self._in_batch:
            del self._data[key]
            return
        with self._lock.gen_wlock():
            del self._data[key]
            self._save()

    def __iter__(self) -> Iterator[str]:
        """Iterate over keys."""
        if self._in_batch:
            return iter(list(self._data))
        with self._lock.gen_rlock():
            return iter(list(self._data))

    def __len__(self) -> int:
        """Return the number of entries."""
        if self._in_batch:
            return len(self._data)
        with self._lock.gen_rlock():
            return len(self._data)

    def __contains__(self, key: object) -> bool:
        """Return True if key exists."""
        if self._in_batch:
            return key in self._data
        with self._lock.gen_rlock():
            return key in self._data

    def values(self) -> list[V]:  # type: ignore[override]
        """Return a snapshot of all values."""
        if self._in_batch:
            return list(self._data.values())
        with self._lock.gen_rlock():
            return list(self._data.values())

    def items(self) -> list[tuple[str, V]]:  # type: ignore[override]
        """Return a snapshot of all key-value pairs."""
        if self._in_batch:
            return list(self._data.items())
        with self._lock.gen_rlock():
            return list(self._data.items())

    def get(self, key: str, default: V | None = None) -> V | None:  # type: ignore[override]
        """Return the value for key, or default if not found."""
        if self._in_batch:
            return self._data.get(key, default)
        with self._lock.gen_rlock():
            return self._data.get(key, default)

    def clear(self) -> None:
        """Remove all entries and persist."""
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
    def batch_write(self) -> Generator["PersistentDict[V]"]:
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
    """Thread-safe JSON-backed list with automatic persistence."""

    def __init__(self, path: str, value_type: type[V]) -> None:
        self._dict: PersistentDict[list[V]] = PersistentDict(path, list[value_type])
        if self._dict.get("items") is None:
            self._dict["items"] = []

    def _get_items(self) -> list[V]:
        return [*self._dict["items"]]

    def _set_items(self, new_items: list[V]) -> None:
        self._dict["items"] = new_items

    def append(self, value: V) -> None:
        """Append a value and persist."""
        items = self._get_items()
        items.append(value)
        self._set_items(items)

    def extend(self, values: list[V]) -> None:
        """Extend the list with values and persist."""
        items = self._get_items()
        items.extend(values)
        self._set_items(items)

    def __getitem__(self, idx: int) -> V:
        """Return the item at index idx."""
        items = self._get_items()
        return items[idx]

    def __setitem__(self, idx: int, value: V) -> None:
        """Set the item at index idx and persist."""
        items = self._get_items()
        items[idx] = value
        self._set_items(items)

    def __delitem__(self, idx: int) -> None:
        """Delete the item at index idx and persist."""
        items = self._get_items()
        del items[idx]
        self._dict["items"] = items

    def __len__(self) -> int:
        """Return the number of items."""
        return len(self._get_items())

    def __iter__(self) -> Iterator[V]:
        """Iterate over items."""
        return iter(self._get_items())

    def clear(self) -> None:
        """Remove all items and persist."""
        self._set_items([])

    def to_list(self) -> list[V]:
        """Return a shallow copy of all items."""
        return self._get_items()


class PersistentObject[V]:
    """A persistent storage for a single object of type V.

    Similar to PersistentList but only stores and manages a single value.
    The value is stored under a fixed key in a PersistentDict.
    """

    _VALUE_KEY = "value"

    def __init__(self, path: str, value_type: type[V], default_value: V | None = None) -> None:
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
    """Property descriptor that persists values to disk via PersistentObject."""

    def __init__(
        self,
        name: str,
        field_type: type[V],
        default_value: V,
        storage_attr: str,
        lock: rwlock.RWLockFair,
    ) -> None:
        self._name = name
        self._field_type = field_type
        self._default_value = default_value
        self._lock = lock
        self._storage_attr = storage_attr

    def _get_storage(self, instance: Any) -> PersistentObject[V]:
        with self._lock.gen_rlock():
            if not isinstance(instance, PersistentPathProvider):
                msg = f"Class {instance.__class__.__name__} must implement PersistentPathProvider"
                raise TypeError(msg)

            # Create storage if it doesn't exist
            if not hasattr(instance, self._storage_attr):
                base_path = instance.get_path()
                file_path = str(Path(base_path) / f"{self._name}.json")
                setattr(
                    instance,
                    self._storage_attr,
                    PersistentObject(file_path, self._field_type, self._default_value),
                )

            return getattr(instance, self._storage_attr)

    def __get__(self, instance: Any, owner: Any) -> V:
        """Return the persistent value for instance."""
        with self._lock.gen_rlock():
            if instance is None:
                return self._default_value
            storage = self._get_storage(instance)
            value = storage.get()
            return value if value is not None else self._default_value

    def __set__(self, instance: Any, value: V) -> None:
        """Persist value on instance."""
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
