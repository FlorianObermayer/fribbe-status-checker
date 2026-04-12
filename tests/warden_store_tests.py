import json
from pathlib import Path

import pytest

from app.services.internal.model import Warden
from app.services.internal.warden_store import WardenStore


@pytest.fixture
def store(tmp_path: Path) -> WardenStore:
    path = str(tmp_path / "wardens.json")
    # Bypass the singleton to get a fresh store backed by a temp file
    return WardenStore(path)


@pytest.fixture
def populated_store(tmp_path: Path) -> WardenStore:
    path = str(tmp_path / "wardens.json")
    store = WardenStore(path)
    store.add(Warden("Alice", ["aa:bb:cc:dd:ee:ff"], ["alices-macbook"]))
    store.add(Warden("Bob", ["11:22:33:44:55:66"]))
    return store


# ---------------------------------------------------------------------------
# get_all
# ---------------------------------------------------------------------------


def test_get_all_empty(store: WardenStore) -> None:
    assert store.get_all() == []


def test_get_all_returns_copy(populated_store: WardenStore) -> None:
    result = populated_store.get_all()
    result.clear()
    assert len(populated_store.get_all()) == 2


# ---------------------------------------------------------------------------
# add
# ---------------------------------------------------------------------------


def test_add_new_warden(store: WardenStore) -> None:
    store.add(Warden("Alice"))
    assert len(store.get_all()) == 1
    assert store.get_all()[0].name == "Alice"


def test_add_duplicate_name_raises(store: WardenStore) -> None:
    store.add(Warden("Alice"))
    with pytest.raises(ValueError, match="already exists"):
        store.add(Warden("Alice"))


def test_add_duplicate_name_case_insensitive(store: WardenStore) -> None:
    store.add(Warden("Alice"))
    with pytest.raises(ValueError, match="already exists"):
        store.add(Warden("alice"))


def test_add_normalises_macs_to_lowercase(store: WardenStore) -> None:
    store.add(Warden("Alice", ["AA:BB:CC:DD:EE:FF"]))
    assert "aa:bb:cc:dd:ee:ff" in store.get_all()[0].device_macs


# ---------------------------------------------------------------------------
# by_name
# ---------------------------------------------------------------------------


def test_by_name_found(populated_store: WardenStore) -> None:
    warden = populated_store.by_name("Alice")
    assert warden.name == "Alice"


def test_by_name_case_insensitive(populated_store: WardenStore) -> None:
    warden = populated_store.by_name("alice")
    assert warden.name == "Alice"


def test_by_name_not_found_raises(store: WardenStore) -> None:
    with pytest.raises(ValueError, match="No warden found"):
        store.by_name("nobody")


# ---------------------------------------------------------------------------
# first_or_none
# ---------------------------------------------------------------------------


def test_first_or_none_match_by_mac(populated_store: WardenStore) -> None:
    result = populated_store.first_or_none("aa:bb:cc:dd:ee:ff", None)
    assert result is not None
    assert result.name == "Alice"


def test_first_or_none_match_by_mac_case_insensitive(populated_store: WardenStore) -> None:
    result = populated_store.first_or_none("AA:BB:CC:DD:EE:FF", None)
    assert result is not None
    assert result.name == "Alice"


def test_first_or_none_match_by_device_name(populated_store: WardenStore) -> None:
    result = populated_store.first_or_none(None, "alices-macbook")
    assert result is not None
    assert result.name == "Alice"


def test_first_or_none_no_match(populated_store: WardenStore) -> None:
    assert populated_store.first_or_none("ff:ff:ff:ff:ff:ff", None) is None


def test_first_or_none_both_none(populated_store: WardenStore) -> None:
    assert populated_store.first_or_none(None, None) is None


# ---------------------------------------------------------------------------
# update
# ---------------------------------------------------------------------------


def test_update_warden(populated_store: WardenStore) -> None:
    updated = Warden("Alice", ["99:88:77:66:55:44"])
    populated_store.update("Alice", updated)
    warden = populated_store.by_name("Alice")
    assert "99:88:77:66:55:44" in warden.device_macs


def test_update_not_found_raises(store: WardenStore) -> None:
    with pytest.raises(ValueError, match="No warden found"):
        store.update("nobody", Warden("nobody"))


def test_update_case_insensitive(populated_store: WardenStore) -> None:
    updated = Warden("Alice", ["99:88:77:66:55:44"])
    populated_store.update("alice", updated)
    assert "99:88:77:66:55:44" in populated_store.by_name("Alice").device_macs


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------


def test_delete_warden(populated_store: WardenStore) -> None:
    populated_store.delete("Alice")
    assert len(populated_store.get_all()) == 1
    with pytest.raises(ValueError):
        populated_store.by_name("Alice")


def test_delete_not_found_raises(store: WardenStore) -> None:
    with pytest.raises(ValueError, match="No warden found"):
        store.delete("nobody")


def test_delete_case_insensitive(populated_store: WardenStore) -> None:
    populated_store.delete("alice")
    with pytest.raises(ValueError):
        populated_store.by_name("Alice")


# ---------------------------------------------------------------------------
# persistence
# ---------------------------------------------------------------------------


def test_persist_and_reload(tmp_path: Path) -> None:
    path = str(tmp_path / "wardens.json")
    s1 = WardenStore(path)
    s1.add(Warden("Alice", ["aa:bb:cc:dd:ee:ff"], ["alice-laptop"]))
    s1.add(Warden("Bob"))

    s2 = WardenStore(path)
    wardens = s2.get_all()
    assert len(wardens) == 2
    alice = s2.by_name("Alice")
    assert alice.device_macs == ["aa:bb:cc:dd:ee:ff"]
    assert alice.device_names == ["alice-laptop"]


def test_persist_delete_and_reload(tmp_path: Path) -> None:
    path = str(tmp_path / "wardens.json")
    s1 = WardenStore(path)
    s1.add(Warden("Alice"))
    s1.add(Warden("Bob"))
    s1.delete("Alice")

    s2 = WardenStore(path)
    assert len(s2.get_all()) == 1
    assert s2.get_all()[0].name == "Bob"


def test_load_missing_file_starts_empty(tmp_path: Path) -> None:
    path = str(tmp_path / "nonexistent.json")
    store = WardenStore(path)
    assert store.get_all() == []


def test_creates_parent_directory_on_save(tmp_path: Path) -> None:
    path = str(tmp_path / "nested" / "dir" / "wardens.json")
    store = WardenStore(path)
    store.add(Warden("Alice"))
    assert Path(path).exists()


def test_json_structure_on_disk(tmp_path: Path) -> None:
    path = str(tmp_path / "wardens.json")
    store = WardenStore(path)
    store.add(Warden("Alice", ["aa:bb:cc:dd:ee:ff"]))

    with Path(path).open(encoding="utf-8") as f:
        data = json.load(f)

    assert "wardens" in data
    assert data["wardens"][0]["name"] == "Alice"
    assert data["wardens"][0]["device_macs"] == ["aa:bb:cc:dd:ee:ff"]


def test_atomic_write_no_temp_files_left(tmp_path: Path) -> None:
    path = str(tmp_path / "wardens.json")
    store = WardenStore(path)
    store.add(Warden("Alice", ["aa:bb:cc:dd:ee:ff"]))
    store.add(Warden("Bob"))
    store.delete("Bob")
    # Only the target JSON file should exist, no .tmp leftovers
    files = list(tmp_path.iterdir())
    assert len(files) == 1
    assert files[0].name == "wardens.json"
