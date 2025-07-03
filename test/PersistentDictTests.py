import os
import tempfile
from typing import Dict, Any
from app.services.PersistentDict import PersistentDict, DictSerializable
from dataclasses import dataclass, asdict

def test_persistentdict_write_and_read():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, "test.json")

        d: PersistentDict[str, int] = PersistentDict(path, int)
        d["foo"] = 123
        d["bar"] = 456
        assert d["foo"] == 123
        assert d["bar"] == 456
        # Reload from file
        d2: PersistentDict[str, int] = PersistentDict(path, int)
        assert d2["foo"] == 123
        assert d2["bar"] == 456

def test_persistentdict_delete():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, "test.json")
        d: PersistentDict[str, int] = PersistentDict(path)
        d["foo"] = 1
        d["bar"] = 2
        del d["foo"]
        assert "foo" not in d
        # Reload from file
        d2: PersistentDict[str, int] = PersistentDict(path)
        assert "foo" not in d2
        assert d2["bar"] == 2

def test_persistentdict_len_and_iter():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, "test.json")
        d : PersistentDict[str, int]= PersistentDict(path)
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
        d = PersistentDict[str, MyClass](path, value_type=MyClass)
        d["a"] = MyClass("hello", 123)
        d["b"] = MyClass("world", 456)
        # Reload
        d2 = PersistentDict[str, MyClass](path, value_type=MyClass)
        assert d2["a"].foo == "hello"
        assert d2["b"].bar == 456


def test_persistentdict_with_dataclass():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, "dataclass.json")
        d = PersistentDict[str, MyDataClass](path, value_type=MyDataClass)
        d["x"] = MyDataClass("foo", 1)
        d["y"] = MyDataClass("bar", 2)
        # Reload
        d2 = PersistentDict[str, MyDataClass](path, value_type=MyDataClass)
        assert d2["x"].foo == "foo"
        assert d2["y"].bar == 2


@dataclass
class MyDataClassWithoutProtocol:
    foo: str
    bar: int


def test_persistentdict_with_dataclass_omitting_protocol():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, "dataclass.json")
        d = PersistentDict[str, MyDataClassWithoutProtocol](
            path, value_type=MyDataClassWithoutProtocol
        )
        d["x"] = MyDataClassWithoutProtocol("foo", 1)
        d["y"] = MyDataClassWithoutProtocol("bar", 2)
        # Reload
        d2 = PersistentDict[str, MyDataClassWithoutProtocol](
            path, value_type=MyDataClassWithoutProtocol
        )
        assert d2["x"].foo == "foo"
        assert d2["y"].bar == 2
