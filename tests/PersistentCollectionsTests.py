import tempfile
import threading
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from app.services.PersistentCollections import (
    DictSerializable,
    PersistentDescriptor,
    PersistentDict,
    PersistentList,
    PersistentObject,
    PersistentPathProvider,
    persistent,
)


def test_persistentdict_write_to_non_existing_subfolder():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = str(Path(tmpdir) / "subfolder" / "in_subfolder.json")
        d = PersistentDict(path, int)
        d["foo"] = 123
        d2: PersistentDict[int] = PersistentDict(path, int)
        assert d2["foo"] == 123


def test_persistentdict_write_and_read():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = str(Path(tmpdir) / "test.json")

        d = PersistentDict(path, int)
        d["foo"] = 123
        d["bar"] = 456
        assert d["foo"] == 123
        assert d["bar"] == 456
        # Reload from file
        d2: PersistentDict[int] = PersistentDict(path, int)
        assert d2["foo"] == 123
        assert d2["bar"] == 456


def test_persistentdict_delete():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = str(Path(tmpdir) / "test.json")
        d: PersistentDict[int] = PersistentDict(path, int)
        d["foo"] = 1
        d["bar"] = 2
        del d["foo"]
        assert "foo" not in d
        # Reload from file
        d2: PersistentDict[int] = PersistentDict(path, int)
        assert "foo" not in d2
        assert d2["bar"] == 2


def test_persistentdict_len_and_iter():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = str(Path(tmpdir) / "test.json")
        d: PersistentDict[int] = PersistentDict(path, int)
        d["a"] = 1
        d["b"] = 2
        d["c"] = 3
        assert len(d) == 3
        keys = set(d)
        assert keys == {"a", "b", "c"}


# Class using DictSerializable
class MyClass(DictSerializable):
    def __init__(self, foo: str, bar: int):
        self.foo = foo
        self.bar = bar

    def to_dict(self) -> dict[str, Any]:
        return {"foo": self.foo, "bar": self.bar}

    @classmethod
    def from_dict(cls, d: dict[str, Any]):
        return cls(d["foo"], d["bar"])


# DataClass using DictSerializable
@dataclass
class MyDataClass(DictSerializable):
    foo: str
    bar: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]):
        return cls(**d)


def test_persistentdict_with_class():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = str(Path(tmpdir) / "class.json")
        d = PersistentDict[MyClass](path, value_type=MyClass)
        d["a"] = MyClass("hello", 123)
        d["b"] = MyClass("world", 456)
        # Reload
        d2 = PersistentDict[MyClass](path, value_type=MyClass)
        assert d2["a"].foo == "hello"
        assert d2["b"].bar == 456


def test_persistentdict_with_class_in_list():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = str(Path(tmpdir) / "class_in_list.json")
        d = PersistentDict[list[MyClass]](path, value_type=list[MyClass])
        d["a"] = [MyClass("hello", 123)]
        d["b"] = [MyClass("world", 456)]
        # Reload
        d2 = PersistentDict[list[MyClass]](path, value_type=list[MyClass])
        assert d2["a"][0].foo == "hello"
        assert d2["b"][0].bar == 456


def test_persistentdict_with_dataclass():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = str(Path(tmpdir) / "dataclass.json")
        d = PersistentDict[MyDataClass](path, value_type=MyDataClass)
        d["x"] = MyDataClass("foo", 1)
        d["y"] = MyDataClass("bar", 2)
        # Reload
        d2 = PersistentDict[MyDataClass](path, value_type=MyDataClass)
        assert d2["x"].foo == "foo"
        assert d2["y"].bar == 2


@dataclass
class MyDataClassWithoutProtocol:
    foo: str
    bar: int


def test_persistentdict_with_dataclass_omitting_protocol_expect_type_error():
    with pytest.raises(TypeError):
        _ = PersistentDict[MyDataClassWithoutProtocol]("my_path", value_type=MyDataClassWithoutProtocol)


# Nested DictSerializable class for testing
class NestedClass(DictSerializable):
    def __init__(self, name: str, values: list[int], child: "None | NestedClass" = None):
        self.name = name
        self.values = values
        self.child = child

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "values": self.values,
            "child": self.child.to_dict() if self.child else None,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]):
        child = cls.from_dict(d["child"]) if d["child"] else None
        return cls(d["name"], d["values"], child)


def test_persistentdict_nested_dictserializable():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = str(Path(tmpdir) / "nested.json")
        nested = NestedClass("root", [1, 2], NestedClass("child", [3, 4]))
        d = PersistentDict[NestedClass](path, value_type=NestedClass)
        d["n"] = nested
        # Reload
        d2 = PersistentDict[NestedClass](path, value_type=NestedClass)
        assert d2["n"].name == "root"
        assert d2["n"].values == [1, 2]
        assert d2["n"].child.name == "child"  # type: ignore
        assert d2["n"].child.values == [3, 4]  # type: ignore
        assert d2["n"].child.child is None  # type: ignore


def test_persistentdict_nested_dict():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = str(Path(tmpdir) / "nested_dict.json")
        nested_dict: dict[str, dict[int, dict[str, int]]] = {"a": {1: {"b": 1}}}
        d = PersistentDict(path, value_type=dict[str, dict[int, dict[str, int]]])
        d["nested"] = nested_dict
        d2 = PersistentDict(path, value_type=dict[str, dict[int, dict[str, int]]])
        assert d2["nested"]["a"][1]["b"] == 1


def test_persistentdict_nested_dict_any_type_not_supported():
    with pytest.raises(TypeError):
        _ = PersistentDict[dict[str, Any]]("my_path", value_type=dict[str, Any])


def test_persistentdict_nested_list_any_type_not_supported():
    with pytest.raises(TypeError):
        _ = PersistentDict[list[list[list[Any]]]]("my_path", value_type=list[list[list[Any]]])


def test_persistentdict_nested_list():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = str(Path(tmpdir) / "nested_list.json")
        nested_list: list[list[list[int]]] = [[[1, 2], [3, 5]]]
        d = PersistentDict(path, value_type=list[list[list[int]]])
        d["lst"] = nested_list
        d2 = PersistentDict(path, value_type=list[list[list[int]]])
        assert d2["lst"][0][1][1] == 5


def test_persistentlist_with_union_types_not_supported():
    with pytest.raises(TypeError):
        _ = PersistentDict("path", value_type=list[int | list[int]])


def test_persistentlist_with_int():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = str(Path(tmpdir) / "list.json")
        lst = PersistentList(path, int)
        lst.append(1)
        lst.append(2)
        lst.append(3)
        assert lst.to_list() == [1, 2, 3]
        # Reload
        l2 = PersistentList(path, int)
        assert l2.to_list() == [1, 2, 3]
        l2.clear()
        assert l2.to_list() == []


def test_persistentlist_with_class():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = str(Path(tmpdir) / "list.json")
        lst = PersistentList(path, MyClass)
        lst.append(MyClass("a", 1))
        lst.append(MyClass("b", 2))
        assert lst[0].foo == "a"
        assert lst[1].bar == 2
        # Reload
        l2 = PersistentList(path, MyClass)
        assert l2[0].foo == "a"
        assert l2[1].bar == 2


def test_persistentlist_with_dataclass():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = str(Path(tmpdir) / "list.json")
        lst = PersistentList(path, MyDataClass)
        lst.append(MyDataClass("x", 10))
        lst.append(MyDataClass("y", 20))
        assert lst[0].foo == "x"
        assert lst[1].bar == 20
        # Reload
        l2 = PersistentList(path, MyDataClass)
        assert l2[0].foo == "x"
        assert l2[1].bar == 20
        l2.clear()
        assert l2.to_list() == []


def test_persistentdict_with_datetime():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = str(Path(tmpdir) / "datetime.json")
        d = PersistentDict(path, datetime)

        # Test with timezone-aware datetime
        berlin_tz = ZoneInfo("Europe/Berlin")
        now = datetime.now(berlin_tz)
        d["now"] = now
        d["tomorrow"] = now + timedelta(days=1)

        # Reload and verify
        d2 = PersistentDict(path, datetime)

        d2_now = d2["now"]
        d2_tomorrow = d2["tomorrow"]
        assert d2_now == now
        assert d2_tomorrow == now + timedelta(days=1)


def test_persistentdict_with_naive_datetime():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = str(Path(tmpdir) / "naive_datetime.json")
        d = PersistentDict(path, datetime)

        # Test with naive datetime (no timezone)
        naive_now = datetime.now()
        d["naive"] = naive_now

        # Reload and verify
        d2 = PersistentDict(path, datetime)
        assert d2["naive"] == naive_now


def test_persistentlist_with_datetime():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = str(Path(tmpdir) / "datetime_list.json")
        lst = PersistentList(path, datetime)

        berlin_tz = ZoneInfo("Europe/Berlin")
        now = datetime.now(berlin_tz)
        timestamps = [now, now + timedelta(hours=1), now + timedelta(days=1)]

        # Add timestamps to list
        for ts in timestamps:
            lst.append(ts)

        # Verify immediate state
        assert len(lst) == 3
        assert lst[0] == timestamps[0]
        assert lst[1] == timestamps[1]
        assert lst[2] == timestamps[2]

        # Reload and verify
        l2 = PersistentList(path, datetime)
        assert len(l2) == 3
        for i, ts in enumerate(timestamps):
            assert l2[i] == ts


def test_persistentdict_with_mixed_datetime_formats():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = str(Path(tmpdir) / "mixed_datetime.json")
        d = PersistentDict(path, datetime)

        berlin_tz = ZoneInfo("Europe/Berlin")
        utc_tz = ZoneInfo("UTC")

        # Test various datetime formats
        d["berlin"] = datetime.now(berlin_tz)
        d["utc"] = datetime.now(utc_tz)
        d["naive"] = datetime.now()

        # Reload and verify
        d2 = PersistentDict(path, datetime)

        # Naive should be interpreted as Berlin time
        assert d2["berlin"] == d["berlin"]
        assert d2["utc"] == d["utc"]
        assert d2["naive"] == d["naive"]


def test_persistentobject_with_int():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = str(Path(tmpdir) / "object.json")
        obj = PersistentObject(path, int, default_value=42)
        assert obj.get() == 42

        # Test setting a new value
        obj.set(123)
        assert obj.get() == 123

        # Test clearing the value
        obj.clear()
        assert obj.get() is None

        # Test setting None explicitly
        obj.set(456)
        obj.set(None)
        assert obj.get() is None


def test_persistentobject_with_class():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = str(Path(tmpdir) / "object_class.json")
        # Test without default value
        obj = PersistentObject(path, MyClass)
        assert obj.get() is None

        test_obj = MyClass("test", 123)
        obj.set(test_obj)
        assert obj.get().foo == "test"  # type: ignore
        assert obj.get().bar == 123  # type: ignore

        # Reload from file
        obj2 = PersistentObject(path, MyClass)
        assert obj2.get().foo == "test"  # type: ignore
        assert obj2.get().bar == 123  # type: ignore


def test_persistentobject_with_dataclass():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = str(Path(tmpdir) / "object_dataclass.json")
        default_value = MyDataClass("default", 0)
        obj = PersistentObject(path, MyDataClass, default_value=default_value)

        # Test default value
        assert obj.get().foo == "default"  # type: ignore
        assert obj.get().bar == 0  # type: ignore

        # Test setting new value
        new_value = MyDataClass("new", 42)
        obj.set(new_value)

        # Reload and verify
        obj2 = PersistentObject(path, MyDataClass)
        assert obj2.get().foo == "new"  # type: ignore
        assert obj2.get().bar == 42  # type: ignore


def test_persistentobject_with_datetime():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = str(Path(tmpdir) / "object_datetime.json")
        berlin_tz = ZoneInfo("Europe/Berlin")
        now = datetime.now(berlin_tz)

        obj = PersistentObject(path, datetime, default_value=now)
        assert obj.get() == now

        # Test with new datetime
        tomorrow = now + timedelta(days=1)
        obj.set(tomorrow)
        assert obj.get() == tomorrow

        # Reload and verify
        obj2 = PersistentObject(path, datetime)
        assert obj2.get() == tomorrow

        # Test clearing
        obj2.clear()
        assert obj2.get() is None


class DecoratedConfig(PersistentPathProvider):
    def __init__(self, base_path: str):
        self._base_path = base_path

    def get_path(self) -> str:
        return self._base_path

    name: PersistentDescriptor[str] = persistent(str, "name", "default")
    count: PersistentDescriptor[int] = persistent(int, "count", 0)
    data: PersistentDescriptor[MyDataClass] = persistent(MyDataClass, "data", MyDataClass("default", 42))


def test_persistent_decorator():
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create and set properties
        config = DecoratedConfig(tmpdir)
        assert config.name == "default"  # Default value
        assert config.count == 0  # Default value
        assert config.data.foo == "default"  # Default value
        assert config.data.bar == 42

        # Update values
        config.name = "test"
        config.count = 123
        config.data = MyDataClass("updated", 456)

        # Create new instance and verify persistence
        config2 = DecoratedConfig(tmpdir)
        assert config2.name == "test"
        assert config2.count == 123
        assert config2.data.foo == "updated"
        assert config2.data.bar == 456

        # Update in second instance
        config2.name = "changed"

        # First instance sees the update
        assert config.name == "changed"

        # Test nested updates
        config2.data = MyDataClass("nested", 789)
        assert config.data.foo == "nested"
        assert config.data.bar == 789


def test_atomic_write_leaves_valid_file_on_success():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = str(Path(tmpdir) / "atomic.json")
        d: PersistentDict[int] = PersistentDict(path, int)
        d["a"] = 1
        d["b"] = 2
        # File should be valid JSON after writes
        d2: PersistentDict[int] = PersistentDict(path, int)
        assert d2["a"] == 1
        assert d2["b"] == 2


def test_atomic_write_no_temp_files_left():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = str(Path(tmpdir) / "atomic.json")
        d: PersistentDict[int] = PersistentDict(path, int)
        d["x"] = 42
        # Only the target JSON file should exist, no .tmp leftovers
        files = list(Path(tmpdir).iterdir())
        assert len(files) == 1
        assert files[0].name == "atomic.json"


def test_batch_write_saves_once():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = str(Path(tmpdir) / "batch.json")
        d: PersistentDict[int] = PersistentDict(path, int)
        with d.batch_write() as store:
            store["a"] = 1
            store["b"] = 2
            store["c"] = 3
        # Verify all values persisted
        d2: PersistentDict[int] = PersistentDict(path, int)
        assert d2["a"] == 1
        assert d2["b"] == 2
        assert d2["c"] == 3


def test_batch_write_delete():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = str(Path(tmpdir) / "batch_del.json")
        d: PersistentDict[int] = PersistentDict(path, int)
        d["a"] = 1
        d["b"] = 2
        d["c"] = 3
        with d.batch_write() as store:
            del store["a"]
            del store["c"]
        d2: PersistentDict[int] = PersistentDict(path, int)
        assert "a" not in d2
        assert d2["b"] == 2
        assert "c" not in d2


def test_batch_write_clear():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = str(Path(tmpdir) / "batch_clear.json")
        d: PersistentDict[int] = PersistentDict(path, int)
        d["a"] = 1
        d["b"] = 2
        with d.batch_write() as store:
            store.clear()
        d2: PersistentDict[int] = PersistentDict(path, int)
        assert len(d2) == 0


def test_batch_write_exception_still_saves():
    """On exception the batch should still save whatever mutations happened."""
    with tempfile.TemporaryDirectory() as tmpdir:
        path = str(Path(tmpdir) / "batch_exc.json")
        d: PersistentDict[int] = PersistentDict(path, int)
        with pytest.raises(RuntimeError), d.batch_write() as store:
            store["a"] = 1
            raise RuntimeError("oops")
        # The mutation should still be saved
        d2: PersistentDict[int] = PersistentDict(path, int)
        assert d2["a"] == 1


def test_batch_write_read_within_batch():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = str(Path(tmpdir) / "batch_read.json")
        d: PersistentDict[int] = PersistentDict(path, int)
        d["x"] = 10
        with d.batch_write() as store:
            assert store["x"] == 10
            store["x"] = 20
            assert store["x"] == 20
            assert "x" in store
            assert len(store) == 1


def test_batch_write_other_thread_still_locks():
    """Non-batch threads must not skip locking while another thread holds batch_write."""
    with tempfile.TemporaryDirectory() as tmpdir:
        path = str(Path(tmpdir) / "thread_safety.json")
        d: PersistentDict[int] = PersistentDict(path, int)
        d["x"] = 1

        other_done = threading.Event()
        other_value: list[int | None] = [None]

        def other_thread() -> None:
            # This should block until batch_write releases the write lock.
            other_value[0] = d.get("x")
            other_done.set()

        with d.batch_write() as store:
            store["x"] = 42
            t = threading.Thread(target=other_thread)
            t.start()
            # Give the other thread a moment to attempt the read (it should block).
            assert not other_done.wait(timeout=0.15), "Other thread should be blocked by the write lock"

        # After batch_write exits, the other thread should complete.
        t.join(timeout=2)
        assert other_value[0] == 42
