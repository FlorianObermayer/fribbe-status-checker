import os
import tempfile
import json
from typing import List
from app.api.EphemeralAPIKeyStore import EphemeralAPIKeyStore

def test_load_and_save_roundtrip():
    # Use a temp file for isolation
    with tempfile.NamedTemporaryFile() as tmp:
        os.environ["API_KEYS_PATH"] = tmp.name
        keys : List[dict[str,str]] = [
            {"key": "abc123", "comment": "test", "valid_until": "2030-01-01T00:00:00"},
            {"key": "def456", "comment": "test2", "valid_until": None}, # type: ignore
        ]
        EphemeralAPIKeyStore.save(keys)
        loaded = EphemeralAPIKeyStore.load()
        assert loaded == keys

def test_load_returns_empty_on_missing_file():
    with tempfile.NamedTemporaryFile() as tmp:
        os.environ["API_KEYS_PATH"] = tmp.name
        assert EphemeralAPIKeyStore.load() == []

def test_load_returns_empty_on_invalid_file():
    with tempfile.NamedTemporaryFile(mode="w") as tmp:
        tmp.write("not a json")
        tmp_path = tmp.name
        os.environ["API_KEYS_PATH"] = tmp_path
        assert EphemeralAPIKeyStore.load() == []

def test_save_creates_file():
    with tempfile.NamedTemporaryFile() as tmp:
        os.remove(tmp.name)
        os.environ["API_KEYS_PATH"] = tmp.name
        keys = [{"key": "xyz789", "comment": "foo", "valid_until": None}] # type: ignore
        EphemeralAPIKeyStore.save(keys) # type: ignore
        assert os.path.exists(tmp.name)
        with open(tmp.name) as f:
            data = json.load(f)
            assert data == keys

