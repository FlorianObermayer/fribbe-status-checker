import os
import tempfile
from typing import Dict, Any, List
from app.services.PersistentDict import PersistentDict, DictSerializable
from dataclasses import dataclass, asdict
import pytest

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
        nested_dict: Dict[str, Any] = {"a": {"b": {"c": 123}}, "x": [1, 2, {"y": 3}]}
        d = PersistentDict(path, value_type=Dict[str, Any])
        d["nested"] = nested_dict
        d2 = PersistentDict(path, value_type=Dict[str, Any])
        assert d2["nested"]["a"]["b"]["c"] == 123
        assert d2["nested"]["x"][2]["y"] == 3


def test_persistentdict_nested_list():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, "nested_list.json")
        nested_list = [[1, 2], [3, [4, 5]], {"foo": [6, 7]}]  # type: ignore
        d = PersistentDict(path, value_type=list)  # type: ignore
        d["lst"] = nested_list
        d2 = PersistentDict(path, value_type=list)  # type: ignore
        assert d2["lst"][1][1][1] == 5
        assert d2["lst"][2]["foo"][1] == 7
