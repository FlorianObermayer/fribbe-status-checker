import os
import tempfile
from typing import Dict, Any, List
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from app.services.PersistentCollections import (
    PersistentDict,
    PersistentList,
    DictSerializable,
)
from dataclasses import dataclass, asdict
import pytest


def test_persistentdict_write_to_non_existing_subfolder():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, "subfolder", "in_subfolder.json")
        d = PersistentDict(path, int)
        d["foo"] = 123
        d2: PersistentDict[int] = PersistentDict(path, int)
        assert d2["foo"] == 123


def test_persistentdict_write_and_read():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, "test.json")

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
        path = os.path.join(tmpdir, "test.json")
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
        path = os.path.join(tmpdir, "test.json")
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

    def to_dict(self) -> Dict[str, Any]:
        return {"foo": self.foo, "bar": self.bar}

    @classmethod
    def from_dict(cls, d: Dict[str, Any]):
        return cls(d["foo"], d["bar"])


# DataClass using DictSerializable
@dataclass
class MyDataClass(DictSerializable):
    foo: str
    bar: int

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]):
        return cls(**d)


def test_persistentdict_with_class():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, "class.json")
        d = PersistentDict[MyClass](path, value_type=MyClass)
        d["a"] = MyClass("hello", 123)
        d["b"] = MyClass("world", 456)
        # Reload
        d2 = PersistentDict[MyClass](path, value_type=MyClass)
        assert d2["a"].foo == "hello"
        assert d2["b"].bar == 456


def test_persistentdict_with_class_in_list():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, "class_in_list.json")
        d = PersistentDict[List[MyClass]](path, value_type=List[MyClass])
        d["a"] = [MyClass("hello", 123)]
        d["b"] = [MyClass("world", 456)]
        # Reload
        d2 = PersistentDict[List[MyClass]](path, value_type=List[MyClass])
        assert d2["a"][0].foo == "hello"
        assert d2["b"][0].bar == 456


def test_persistentdict_with_dataclass():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, "dataclass.json")
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
        _ = PersistentDict[MyDataClassWithoutProtocol](
            "my_path", value_type=MyDataClassWithoutProtocol
        )


# Nested DictSerializable class for testing
class NestedClass(DictSerializable):
    def __init__(
        self, name: str, values: List[int], child: "None | NestedClass" = None
    ):
        self.name = name
        self.values = values
        self.child = child

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "values": self.values,
            "child": self.child.to_dict() if self.child else None,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]):
        child = cls.from_dict(d["child"]) if d["child"] else None
        return cls(d["name"], d["values"], child)


def test_persistentdict_nested_dictserializable():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, "nested.json")
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
        path = os.path.join(tmpdir, "nested_dict.json")
        nested_dict: Dict[str, Dict[int, Dict[str, int]]] = {"a": {1: {"b": 1}}}
        d = PersistentDict(path, value_type=Dict[str, Dict[int, Dict[str, int]]])
        d["nested"] = nested_dict
        d2 = PersistentDict(path, value_type=Dict[str, Dict[int, Dict[str, int]]])
        assert d2["nested"]["a"][1]["b"] == 1


def test_persistentdict_nested_dict_any_type_not_supported():
    with pytest.raises(TypeError):
        _ = PersistentDict[Dict[str, Any]]("my_path", value_type=Dict[str, Any])


def test_persistentdict_nested_list_any_type_not_supported():
    with pytest.raises(TypeError):
        _ = PersistentDict[List[List[List[Any]]]](
            "my_path", value_type=List[List[List[Any]]]
        )


def test_persistentdict_nested_list():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, "nested_list.json")
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
        path = os.path.join(tmpdir, "list.json")
        l = PersistentList(path, int)
        l.append(1)
        l.append(2)
        l.append(3)
        assert l.to_list() == [1, 2, 3]
        # Reload
        l2 = PersistentList(path, int)
        assert l2.to_list() == [1, 2, 3]
        l2.clear()
        assert l2.to_list() == []


def test_persistentlist_with_class():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, "list.json")
        l = PersistentList(path, MyClass)
        l.append(MyClass("a", 1))
        l.append(MyClass("b", 2))
        assert l[0].foo == "a"
        assert l[1].bar == 2
        # Reload
        l2 = PersistentList(path, MyClass)
        assert l2[0].foo == "a"
        assert l2[1].bar == 2


def test_persistentlist_with_dataclass():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, "list.json")
        l = PersistentList(path, MyDataClass)
        l.append(MyDataClass("x", 10))
        l.append(MyDataClass("y", 20))
        assert l[0].foo == "x"
        assert l[1].bar == 20
        # Reload
        l2 = PersistentList(path, MyDataClass)
        assert l2[0].foo == "x"
        assert l2[1].bar == 20
        l2.clear()
        assert l2.to_list() == []


def test_persistentdict_with_datetime():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, "datetime.json")
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
        path = os.path.join(tmpdir, "naive_datetime.json")
        d = PersistentDict(path, datetime)

        # Test with naive datetime (no timezone)
        naive_now = datetime.now()
        d["naive"] = naive_now

        # Reload and verify
        d2 = PersistentDict(path, datetime)
        assert d2["naive"] == naive_now


def test_persistentlist_with_datetime():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, "datetime_list.json")
        l = PersistentList(path, datetime)

        berlin_tz = ZoneInfo("Europe/Berlin")
        now = datetime.now(berlin_tz)
        timestamps = [now, now + timedelta(hours=1), now + timedelta(days=1)]

        # Add timestamps to list
        for ts in timestamps:
            l.append(ts)

        # Verify immediate state
        assert len(l) == 3
        assert l[0] == timestamps[0]
        assert l[1] == timestamps[1]
        assert l[2] == timestamps[2]

        # Reload and verify
        l2 = PersistentList(path, datetime)
        assert len(l2) == 3
        for i, ts in enumerate(timestamps):
            assert l2[i] == ts


def test_persistentdict_with_mixed_datetime_formats():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, "mixed_datetime.json")
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
